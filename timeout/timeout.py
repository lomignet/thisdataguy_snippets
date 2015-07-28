#!/usr/bin/env python
import argparse
import socket
import time


# Make the TimeoutServer a bit more user friendly by giving 3 options:
# --http/-w to return a valid http response
# --port/-p to define the port to listen to (7000)
# --timeout/-t to define the timeout delay (5)

parser = argparse.ArgumentParser(description='Timeout Server.')
parser.add_argument('--http', '-w', default=False, dest='http', action='store_true',
                    help='if true return a valid http 204 response.')
parser.add_argument('--port', '-p', type=int, default=7000, dest='port',
                    help='Port to listen to. Default 7000.')
parser.add_argument('--timeout', '-t', type=int, default=5, dest='timeout',
                    help='Timeout in seconds before answering/closing. Default 5.')
args = parser.parse_args()


# Creates a standard socket and listen to incoming connections
# See https://docs.python.org/2/howto/sockets.html for more info
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('127.0.0.1', args.port))
s.listen(5)  # See doc for the explanation of 5. This is a usual value.

while True:
    print("Listening, waiting for connection...")
    (clientsocket, address) = s.accept()
    print("Connected! Timing out after {} seconds...".format(args.timeout))
    time.sleep(args.timeout)
    print('Processing complete.')

    if args.http:
        print("Returning http 204 response.")
        clientsocket.send(
            'HTTP/1.1 204 OK\n'
            #'Date: {0}\n'.format(time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime())
            'Server: Timeout-Server\n'
            'Connection: close\n\n'  # signals no more data to be sent)
        )

    print("Closing connection.\n")
    clientsocket.close()
