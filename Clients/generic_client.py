# -*- coding: utf-8 -*-
import random
import socket
import struct
import sys
import time

from enum import IntEnum

ALPHABET_GENETIQUE = "UGCA"

class ClientOpcode(IntEnum):
    AUTH = 1
    INFECTION = 2
    DISCONNECTION = 3

class ServerOpcode(IntEnum):
    RESULT_INFECTION = 1
    MAXIMUM_INFECTION = 2
    NEW_PLAYER = 3
    INFECTION_OCCURRED = 4
    PLAYER_DISCONNECTED = 5
    NETWORK_SIZE_ANNOUNCEMENT = 6

class InfectionResult(IntEnum):
	PLAIN = 1
	MAXIMUM_REACHED = 2

generation_codes = []

def remplacer_caractere(string, indice_i, caractere):
	lst = list(string)
	lst[indice_i] = caractere
	return ''.join(lst)

def generer_sequence_aleatoire(elements, nombre):
	seq = str()
	for x in range(nombre):
		seq += random.choice(elements)
	return seq

def generer_code_aleatoire(longueur):
	return generer_sequence_aleatoire(ALPHABET_GENETIQUE, longueur)

def generer_mutation(generation):
	return generer_code_aleatoire(8)

class VirusGameClient(object):

	def __init__(self, ip, player_id):
		TCP_SERVER_IP = ip
		TCP_PORT = 5481
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.connect((TCP_SERVER_IP, TCP_PORT))

		packet_auth = struct.pack('!BH', ClientOpcode.AUTH, player_id)
		self.socket.sendall(packet_auth)

		opcode, = struct.unpack('!B', self.socket.recv(1))
		if opcode == ServerOpcode.NETWORK_SIZE_ANNOUNCEMENT:
			self.net_size, = struct.unpack('!I', self.socket.recv(4))
		else:
			raise Exception("Unk opcode: {op}!".format(op=opcode))

	def send_infection(self, code):
		packet_code = struct.pack('!B8s', ClientOpcode.INFECTION, code)
		self.socket.sendall(packet_code)

		data = self.socket.recv(1)
		if data == '':
			print "Failed to infect."
			return None

		opcode, = struct.unpack('!B', data)
		if opcode == ServerOpcode.RESULT_INFECTION:
			result = struct.unpack('!II', self.socket.recv(8))
			return InfectionResult.PLAIN, result
		elif opcode == ServerOpcode.MAXIMUM_INFECTION:
			result, = struct.unpack('!I', self.socket.recv(4))
			return InfectionResult.MAXIMUM_REACHED, result
		else:
			return None

	def send_end(self):
		packet_end = struct.pack('!B', ClientOpcode.DISCONNECTION)
		self.socket.sendall(packet_end)


def main():
	player_id = int(sys.argv[1])
	ip = "80.112.131.85" # Default server
	nb_tentatives = 1
	if len(sys.argv) > 2:
		ip = sys.argv[2]
	if len(sys.argv) > 3:
		nb_tentatives = int(sys.argv[3])

	generation_i = 0

	Running = True

	client = VirusGameClient(ip, player_id)
	print "Processus d'infection démarré!"
	for tentative_i in range(nb_tentatives*client.net_size):
		code_genetique = generer_mutation(generation_i)
		type_resultat, resultat = client.send_infection(code_genetique)
		if resultat is not None:
			if type_resultat == InfectionResult.PLAIN:
				print """
				Résultat de la génération {gi} ({cur}/{max}) : infection {msg}
				""".format(gi=tentative_i+1, cur=resultat[0], max=client.net_size, msg=("Réussie" if resultat[1] else "Ratée"))
			elif type_resultat == InfectionResult.MAXIMUM_REACHED:
				print 'Resultat de la génération {}:\n\tTous les ordinateurs ont été infecté avec succès : {}.'.format(tentative_i, resultat)
	print "Processus d'infection terminé!"
	client.send_end()

if __name__ == '__main__':
	main()       