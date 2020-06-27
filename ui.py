import sys
import time
import threading
from settings import LOGGING
import logging, logging.config
from logging.handlers import TimedRotatingFileHandler
from logging.handlers import RotatingFileHandler
import traceback
import queue
# import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkthread import tk, TkThread
from email_crawler import crawl, crawler_main, OutputUIInterface

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

global main_window
ui_callback_queue = queue.Queue()

class OutputUI(OutputUIInterface):
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
		ctrl.see(tk.END)
		ctrl['state'] = 'disabled'


class MainThreadUI(OutputUIInterface):
	'''can be accessed from worker thread
	dispatch msg to main thread object
	'''

	def __init__(self, output_ui: OutputUIInterface):
		self._output_ui = output_ui

	def append(self, ls):
		# dispatch to main thread
		put_ui_queue(lambda: self._output_ui.append(ls))

	def append_line(self, line):
		# dispatch to main thread
		put_ui_queue(lambda: self._output_ui.append_line(line))

def async_crawl(keyword, output_ui: OutputUIInterface):
	async_output_ui = MainThreadUI(output_ui)

	# runner = CrawlRunner(keyword, output_ui)
	t = threading.Thread(target=crawl, args=(keyword, async_output_ui,), name="crawler")
	t.start()

def test_crawl(keywords, output_ui):
	for i in range(100):
		time.sleep(1)
		output_ui.append([str(i), "check", "hello"])

def async_test_crawl(keyword, output_ui: OutputUI):
	async_output_ui = MainThreadUI(output_ui)

	# runner = CrawlRunner(keyword, output_ui)
	t = threading.Thread(target=test_crawl, args=(keyword, async_output_ui,), name="crawler")
	t.start()

def peek_ui_queue_slowly():
	while True:
		try:
			callback = ui_callback_queue.get(False)
		except:
			break

		callback()

	main_window.after(1000, peek_ui_queue_slowly)

def put_ui_queue(callback):
	ui_callback_queue.put(callback)

if __name__ == "__main__":
	# main(sys.argv)
	# test()
	# testParseLocal()

	# https://realpython.com/python-gui-tkinter/#:~:text=Python%20has%20a%20lot%20of,Windows%2C%20macOS%2C%20and%20Linux.&text=Although%20Tkinter%20is%20considered%20the,framework%2C%20it's%20not%20without%20criticism.
	main_window = window = tk.Tk()
	
	# mani frame随外部窗口拉伸
	frm_main = tk.Frame(borderwidth=3)
	frm_main.pack(fill=tk.BOTH, expand=True)

	ent_keyword = tk.Entry(master=frm_main, width=50)
	ent_keyword.pack()

	btn_search = tk.Button(master=frm_main, text=r"搜索", width=8)
	btn_search.pack()

	# 搜索结果在main frame内自动拉伸
	txt_result = ScrolledText(master=frm_main, state='disabled')
	txt_result.pack(fill=tk.BOTH, expand=True)

	btn_export = tk.Button(master=frm_main, text=r"导出所有地址", width=10)
	btn_export.pack(side=tk.BOTTOM)

	# bind event
	output = OutputUI(txt_result)
	def handle_search(e):
		keyword = ent_keyword.get()
		if keyword and len(keyword) > 2:
			# disable btn style will will not disable event binding
			btn_search['state'] = tk.DISABLED
			btn_search.unbind("<Button-1>", search_bind_id)
			async_test_crawl(keyword, output)
			# async_crawl(keyword, output)

	global search_bind_id
	search_bind_id = btn_search.bind("<Button-1>", handle_search)

	def handle_export(e):
		# todo: export
		pass

	global export_bind_id
	export_bind_id = btn_export.bind("<Button-1>", handle_export)

	peek_ui_queue_slowly()
	window.mainloop()

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

