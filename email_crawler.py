import sys
import string
from settings import LOGGING
import logging, logging.config
from logging.handlers import TimedRotatingFileHandler
from logging.handlers import RotatingFileHandler
import urllib.request, urllib.parse, urllib.error, urllib.request, urllib.error, urllib.parse
import ssl
import re, urllib.parse
import traceback
from database import CrawlerDb

DEFAULT_SITE = r"www.google.com"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Debugging
# import pdb;pdb.set_trace()

# Logging
#logging.config.dictConfig(LOGGING)
logger = logging.getLogger("crawler_logger")

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
MAX_SEARCH_RESULTS = 100

EMAILS_FILENAME = 'data/emails.csv'
DOMAINS_FILENAME = 'data/domains.csv'

class OutputUIInterface:
	def append(self, ls):
		pass

	def append_line(self, line):
		pass

def crawl(site, keywords, output_ui: OutputUIInterface = None):
	# Set up the database
	global db
	db = CrawlerDb(site)
	db.connect()

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
		url = 'http://%s/search?' % site
		url = url + urllib.parse.urlencode(query) + '&start=' + str(page_index)
		# query = {'wd': keywords}
		# url = 'http://www.baidu.com/s?' + urllib.parse.urlencode(query) + '&pn=' + str(page_index)
		
		try:
			data = retrieve_html(url)
			# 	print("data: \n%s" % data)
			for url in google_url_regex.findall(data):
				db.enqueue(str(url))
			for url in google_adurl_regex.findall(data):
				db.enqueue(str(url))
		except Exception as e:
			logger.error(e)

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
		email_set = find_emails_2_level_deep(uncrawled.url, output_ui)
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
		with urllib.request.urlopen(req, timeout=30, context=ctx) as f:
			data = f.read()

		# request = urllib.request.urlopen(req)
	except urllib.error.HTTPError as e:
		status = e.code
	except urllib.error.URLError as e:
		logger.error("Exception at url: %s\n%s" % (url, e))
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


def find_emails_2_level_deep(url, output_ui: OutputUIInterface):
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
			if output_ui:
				output_ui.append(list(email_set))
			db.enqueue(link, list(email_set))

		# We return an empty set
		return set()


def find_emails_in_html(html):
	if (html == None):
		return set()
	email_set = set()
	for email in email_regex.findall(html):
		# ignore image name
		if email.endswith(".png") or email.endswith(".jpg"):
			continue

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

def testParseLocal():
	with open("pagecache.html", "r") as input:
		content = input.read()

	for url in google_url_regex.findall(content):
		print(url)
	for url in google_adurl_regex.findall(content):
		print(url)

def export_emails(site):
	# Set up the database
	db_export = CrawlerDb(site)
	db_export.connect()

	logger.info("="*40)
	logger.info("Processing...")
	emails = db_export.get_all_emails()
	logger.info("There are %d emails" % len(emails))
	file = open(EMAILS_FILENAME, "w+")
	file.writelines("\n".join(emails))
	file.close()
	logger.info("All emails saved to ./data/emails.csv")
	logger.info("="*40)

def export_domains(site):
	db_export = CrawlerDb(site)
	db_export.connect()

	logger.info("="*40)
	logger.info("Processing...")
	domains = db_export.get_all_domains()
	logger.info("There are %d domains" % len(domains))
	file = open(DOMAINS_FILENAME, "w+")
	file.writelines("\n".join(domains))
	file.close()
	logger.info("All domains saved to ./data/domains.csv")
	logger.info("="*40)

def crawler_main(argv):
	try:
		arg = argv[1].lower()
		if (arg == '--emails') or (arg == '-e'):
			# Get all the emails and save in a CSV
			export_emails(site=DEFAULT_SITE)
		elif (arg == '--domains') or (arg == '-d'):
			# Get all the domains and save in a CSV
			export_domains(site=DEFAULT_SITE)
		else:
			# Crawl the supplied keywords!
			crawl(site=DEFAULT_SITE, keywords=arg)

	except KeyboardInterrupt:
		logger.error("Stopping (KeyboardInterrupt)")
		sys.exit()
	except Exception as e:
		logger.error("EXCEPTION: %s " % e)
		traceback.print_exc()

if __name__ == "__main__":
	crawler_main(sys.argv)
	# main(sys.argv)
	# test()
	# testParseLocal()


