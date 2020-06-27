import sys
from settings import LOGGING
import logging, logging.config
from logging.handlers import TimedRotatingFileHandler
from logging.handlers import RotatingFileHandler
import urllib.request, urllib.parse, urllib.error, urllib.request, urllib.error, urllib.parse
import ssl
import re, urllib.parse
import traceback
import tkinter as tk
from database import CrawlerDb

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Debugging
# import pdb;pdb.set_trace()

# Logging
#logging.config.dictConfig(LOGGING)
logger = logging.getLogger("crawler_logger")
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler('logs/log','midnight',1,30)
formatter = logging.Formatter('%(asctime)s %(name)-2s %(levelname)-2s %(message)s','%y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)

google_adurl_regex = re.compile('adurl=(.*?)"')
google_url_regex = re.compile('url\?q=(.*?)&amp;sa=')
email_regex = re.compile('([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4})', re.IGNORECASE)
url_regex = re.compile('<a\s.*?href=[\'"](.*?)[\'"].*?>')
# Below url_regex will run into 'Castrophic Backtracking'!
# http://stackoverflow.com/questions/8010005/python-re-infinite-execution
# url_regex = re.compile('<a\s(?:.*?\s)*?href=[\'"](.*?)[\'"].*?>')

baidu_url_regex = re.compile('url\?q=(.*?)&amp;sa=')
baidu_adurl_regex = re.compile('adurl=(.*?)"')

# Maximum number of search results to start the crawl
MAX_SEARCH_RESULTS = 10

EMAILS_FILENAME = 'data/emails.csv'
DOMAINS_FILENAME = 'data/domains.csv'

# Set up the database
db = CrawlerDb()
db.connect()

class OutputUI:
	def __init__(self, ctrl: tk.Text):
		self._ctrl = ctrl

	def append(self, ls):
		for line in ls:
			self.append_line(line)

	def append_line(self, line):
		ctrl = self._ctrl
		numlines = int(ctrl.index('end - 1 line').split('.')[0])
		ctrl['state'] = 'normal'
		if numlines >= 100:
			ctrl.delete(1.0, 2.0)
		if ctrl.index('end-1c')!='1.0':
			ctrl.insert('end', '\n')
		ctrl.insert('end', line)
		ctrl['state'] = 'disabled'
		


def crawl(keywords, output_ui: OutputUI = None):
	"""
	This method will

	1) Google the keywords, and extract MAX_SEARCH_RESULTS
	2) For every result (aka website), crawl the website 2 levels deep.
		That is the homepage (level 1) and all it's links (level 2).
		But if level 1 has the email, then skip going to level 2.
	3) Store the html in /data/html/ and update the database of the crawled emails

	crawl(keywords):
		Extract Google search results and put all in database
		Process each search result, the webpage:
			Crawl webpage level 1, the homepage
			Crawl webpage level 2, a link away from the homepage
			Update all crawled page in database, with has_crawled = True immediately
			Store the HTML
	"""
	logger.info("-"*40)
	# logger.info("Keywords to Google for: %s" % keywords.decode('utf-8'))
	logger.info("Keywords to Google for: %s" % keywords)
	logger.info("-"*40)

	# Step 1: Crawl Google Page
	# eg http://www.google.com/search?q=singapore+web+development&start=0
	# Next page: https://www.google.com/search?q=singapore+web+development&start=10
	# Google search results are paged with 10 urls each. There are also adurls
	for page_index in range(0, MAX_SEARCH_RESULTS, 10):
		query = {'q': keywords}
		url = 'http://www.google.com/search?' + urllib.parse.urlencode(query) + '&start=' + str(page_index)
		# query = {'wd': keywords}
		# url = 'http://www.baidu.com/s?' + urllib.parse.urlencode(query) + '&pn=' + str(page_index)
		
		data = retrieve_html(url)
		# 	print("data: \n%s" % data)
		for url in google_url_regex.findall(data):
			db.enqueue(str(url))
		for url in google_adurl_regex.findall(data):
			db.enqueue(str(url))

		# for url in baidu_url_regex.findall(data):
		# 	db.enqueue(str(url))
		# for url in baidu_adurl_regex.findall(data):
		# 	db.enqueue(str(url))

	# Step 2: Crawl each of the search result
	# We search till level 2 deep
	while (True):
		# Dequeue an uncrawled webpage from db
		uncrawled = db.dequeue()
		if (uncrawled == False):
			break
		email_set = find_emails_2_level_deep(uncrawled.url)
		if (len(email_set) > 0):
			db.crawled(uncrawled, ",".join(list(email_set)))
			if output_ui:
				output_ui.append(list(email_set))
		else:
			db.crawled(uncrawled, None)

def retrieve_html(url):
	"""
	Crawl a website, and returns the whole html as an ascii string.

	On any error, return.
	"""
	req = urllib.request.Request(url)
	req.add_header('User-Agent', 'Just-Crawling 0.1')
	# request = None
	status = 0
	data = ""
	try:
		logger.info("Crawling %s" % url)
		with urllib.request.urlopen(req, context=ctx) as f:
			data = f.read()

		# request = urllib.request.urlopen(req)
	except urllib.error.URLError as e:
		logger.error("Exception at url: %s\n%s" % (url, e))
	except urllib.error.HTTPError as e:
		status = e.code
	except Exception as e:
		return
	if status == 0:
		status = 200

	# try:
	# 	data = request.read()
	# except Exception as e:
	# 	logger.error(e)
	# 	data = ""

	return str(data)


def find_emails_2_level_deep(url):
	"""
	Find the email at level 1.
	If there is an email, good. Return that email
	Else, find in level 2. Store all results in database directly, and return None
	"""
	html = retrieve_html(url)
	email_set = find_emails_in_html(html)

	if (len(email_set) > 0):
		# If there is a email, we stop at level 1.
		return email_set

	else:
		# No email at level 1. Crawl level 2
		logger.info('No email at level 1.. proceeding to crawl level 2')

		link_set = find_links_in_html_with_same_hostname(url, html)
		for link in link_set:
			# Crawl them right away!
			# Enqueue them too
			html = retrieve_html(link)
			if (html == None):
				continue
			email_set = find_emails_in_html(html)
			db.enqueue(link, list(email_set))

		# We return an empty set
		return set()


def find_emails_in_html(html):
	if (html == None):
		return set()
	email_set = set()
	for email in email_regex.findall(html):
		email_set.add(email)
	return email_set


def find_links_in_html_with_same_hostname(url, html):
	"""
	Find all the links with same hostname as url
	"""
	if (html == None):
		return set()
	url = urllib.parse.urlparse(url)
	links = url_regex.findall(html)
	link_set = set()
	for link in links:
		if link == None:
			continue
		try:
			link = str(link)
			if link.startswith("/"):
				link_set.add('http://'+url.netloc+link)
			elif link.startswith("http") or link.startswith("https"):
				if (link.find(url.netloc)):
					link_set.add(link)
			elif link.startswith("#"):
				continue
			else:
				link_set.add(urllib.parse.urljoin(url.geturl(),link))
		except Exception as e:
			pass

	return link_set

def test():
	keywords = 'python3'

	page = 0
	step = 10
	query = {'wd': keywords}
	url = 'http://www.baidu.com/s?' + urllib.parse.urlencode(query) + '&pn=' + str(page * step)
	data = retrieve_html(url)

	with open("pagecache.html", "w") as output:
		output.write(data)


		# for url in baidu_url_regex.findall(data):
		# 	db.enqueue(str(url))
		# for url in baidu_adurl_regex.findall(data):
		# 	db.enqueue(str(url))

def testLocal():
	with open("pagecache.html", "r") as input:
		content = input.read()

	for url in google_url_regex.findall(content):
		print(url)
	for url in google_adurl_regex.findall(content):
		print(url)

def test_crawl(keywords, output_ui):
	for i in range(100):
		output_ui.append([str(i), "check", "hello"])

def main(argv):
	try:
		arg = argv[1].lower()
		if (arg == '--emails') or (arg == '-e'):
			# Get all the emails and save in a CSV
			logger.info("="*40)
			logger.info("Processing...")
			emails = db.get_all_emails()
			logger.info("There are %d emails" % len(emails))
			file = open(EMAILS_FILENAME, "w+")
			file.writelines("\n".join(emails))
			file.close()
			logger.info("All emails saved to ./data/emails.csv")
			logger.info("="*40)
		elif (arg == '--domains') or (arg == '-d'):
			# Get all the domains and save in a CSV
			logger.info("="*40)
			logger.info("Processing...")
			domains = db.get_all_domains()
			logger.info("There are %d domains" % len(domains))
			file = open(DOMAINS_FILENAME, "w+")
			file.writelines("\n".join(domains))
			file.close()
			logger.info("All domains saved to ./data/domains.csv")
			logger.info("="*40)
		else:
			# Crawl the supplied keywords!
			crawl(arg)

	except KeyboardInterrupt:
		logger.error("Stopping (KeyboardInterrupt)")
		sys.exit()
	except Exception as e:
		logger.error("EXCEPTION: %s " % e)
		traceback.print_exc()

if __name__ == "__main__":
	#import tkinter as tk
	# window = tk.Tk()

	# main(sys.argv)
	# test()
	# testLocal()

	# https://realpython.com/python-gui-tkinter/#:~:text=Python%20has%20a%20lot%20of,Windows%2C%20macOS%2C%20and%20Linux.&text=Although%20Tkinter%20is%20considered%20the,framework%2C%20it's%20not%20without%20criticism.
	window = tk.Tk()

	# mani frame随外部窗口拉伸
	frm_main = tk.Frame(borderwidth=3)
	frm_main.pack(fill=tk.BOTH, expand=True)

	ent_keyword = tk.Entry(master=frm_main, width=50)
	ent_keyword.pack()

	btn_search = tk.Button(master=frm_main, text=r"搜索", width=8)
	btn_search.pack()

	# 搜索结果在main frame内自动拉伸
	txt_result = tk.Text(master=frm_main, state='disabled')
	txt_result.pack(fill=tk.BOTH, expand=True)

	btn_export = tk.Button(master=frm_main, text=r"导出所有地址", width=10)
	btn_export.pack(side=tk.BOTTOM)

	# bind event
	output = OutputUI(txt_result)
	def handle_search(e):
		keyword = ent_keyword.get()
		if keyword and len(keyword) > 2:
			# disable btn
			btn_search['state'] = 'disabled'
			# todo:
			test_crawl(keyword, output)

	btn_search.bind("<Button-1>", handle_search)

	# label = tk.Label(
	# 	text="Hello, Tkinter",
	# 	fg="white",
	# 	bg="black",
	# 	width=10,
	# 	height=10
	# )

	# button = tk.Button(
	# 	text="Click me!",
	# 	width=25,
	# 	height=5,
	# 	bg="blue",
	# 	fg="yellow",
	# )

	# text_box = tk.Text()
	# text_box.pack()
	# text_box.get("1.0", tk.END)

	# frame = tk.Frame()
	# frame.pack()

	# frame = tk.Frame()
	# label = tk.Label(master=frame)

	# label.place(x=0, y=0)

	window.mainloop()

