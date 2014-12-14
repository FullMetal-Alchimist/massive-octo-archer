from gevent import Greenlet, sleep, event, queue

from flask import Flask
from flask import render_template

from flask.ext.socketio import SocketIO
from json import dumps

import zmq

app = Flask(__name__)
app.config['SECRET_KEY'] = '\x1234uaqz~{^@~\iazieojh'

context = zmq.Context()

socketio = SocketIO(app)

EVENT_PUBLISHER_PORT = 5488

queue_buffer = queue.Queue()
processed_buffer = queue.Queue()

def worker_emitter():
	for item in processed_buffer:
		sleep(0.2)
		socketio.emit(item[0] + '_processed', dumps(item[1]))

def worker_processor():
	while True:
		tmp_queue = {}
		count_item = 0
		for item in queue_buffer:
			if item[0] not in tmp_queue:
				tmp_queue[item[0]] = []

			tmp_queue[item[0]] += [item[1]]
			count_item += 1

			if count_item > 125:
				count_item = 0
				for key, item in tmp_queue.items():
					processed_buffer.put([key, item])
				tmp_queue.clear()
		# Flush anyway
		for key, item in tmp_queue.items():
			processed_buffer.put([key, item])
			tmp_queue.clear()


def background_thread():
	z_socket = context.socket(zmq.SUB)
	z_socket.bind("tcp://127.0.0.1:{port}".format(port=EVENT_PUBLISHER_PORT))
	z_socket.setsockopt(zmq.SUBSCRIBE, '')

	print 'Connecting through the TCP system...'
	while True:
		try:
			string = z_socket.recv(zmq.NOBLOCK)
			data = string.split(" ")

			e_type = data[0].lower()

			item = [e_type, data[1:]]
			queue_buffer.put(item)
		except:
			queue_buffer.put(StopIteration)
			sleep(1)

background_thread_spawned = False

@socketio.on('connect')
def handle_connection():
	global background_thread_spawned
	if not background_thread_spawned:
		background_thread_spawned = True
		Greenlet.spawn(background_thread)
		Greenlet.spawn(worker_emitter)
		Greenlet.spawn(worker_processor)
		print 'Realtime thread spawned and workers spawned.'

@socketio.on_error()
def error_handler(e):
	print 'Error happened on Socket.IO: {error}'.format(error=str(e))

@app.route('/events')
def show_realtime_chart():
	return render_template('realtime_chart.html')

if __name__ == '__main__':
	socketio.run(app, host='0.0.0.0', port=5462)