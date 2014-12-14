# Game
import random
import time

# Network
import zmq
import SocketServer

# Serialization
import struct

# Utils
from functools import partial
import dis
from threading import Thread, Timer, RLock
import os
from enum import IntEnum

# Logging utils
import logging
from logging import StreamHandler, FileHandler
from logging import Formatter


# OPCODES
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


# GAME CONSTANTS
class NetworkValueState(IntEnum):
    COMPUTER_ALIVE = 1

GAME_PREDICAT_LEVEL = [ [lambda x: x[0] == 'G',
                        lambda x: x[0] == 'U',
                        lambda x: x[0] == 'A',
                        lambda x: x[0] == 'C'
                        ],
                        [lambda x: x.endswith("GCC"),
                        lambda x: x.endswith("GCU"),
                        lambda x: x.endswith("UGC"),
                        lambda x: x.endswith("CCC")] ]
GAME_DIFFICULTY = 1

# LOGGERS
network_events = logging.getLogger('Network Events')
game_events = logging.getLogger('Game Events')
api_events = logging.getLogger('API Events')

# NETWORK ZMQ CONTEXT
context = zmq.Context()

class PredicatSystem:
    class PredicatSystemEval:
        def __init__(self, system, arg):
            self.system = system
            self.arg = arg

        def __nonzero__(self):
            val = True
            for pred in self.system:
                val = val and pred(self.arg)
            return val

        def __repr__(self):
            return "<Eval: (system={syst}, arg={arg})>".format(syst=self.system, arg=self.arg)


    def always_true(arg):
        return True

    def __init__(self, difficulty):
        self.difficulty = difficulty
        self.system = [PredicatSystem.always_true] * self.difficulty

    def set_difficulty(self, new_difficulty):
        self.system = [PredicatSystem.always_true] * new_difficulty
        self.difficulty = new_difficulty

    def construct_random_system(self, predicats_available_level):
        game_events.debug("Constructing random system of predicats with difficulty of {diff}...".format(diff=self.difficulty))
        for level_idx in range(self.difficulty):
            predicats_available = predicats_available_level[level_idx]
            self.system[level_idx] = random.choice(predicats_available)

    def eval_system(self, arg):
        return self.PredicatSystemEval(self.system, arg)


class Network:
    def always_true(arg):
        return True

    def _init(self, size):
        self.size = size
        self.state = [NetworkValueState.COMPUTER_ALIVE] * size
        self.predicat_system = [PredicatSystem(GAME_DIFFICULTY)] * size

    def __init__(self, size, game, rlock):
        self._init(size)
        self.game = game
        self.rlock = rlock

    def set_new_size(self, size):
        self._init(size)

    def set_state(self, c_id, new_state):
        assert c_id >= 0 and c_id < self.size
        self.state[c_id] = new_state

    def construct_random_network(self):
        game_events.debug("Constructing a random network (size {network_size}) with a system of predicats...".format(network_size=self.size))
        for x in range(self.size):
            self.predicat_system[x].construct_random_system(GAME_PREDICAT_LEVEL)
        game_events.debug("Network constructed.")

    def randomize_network(self):
        game_events.info("Network randomization procedure has been started.")
        for x in range(self.size):
            chance_av_detection_trigger = 50.0/100.0 # 50% of chance
            triggered = random.uniform(0, 1) >= chance_av_detection_trigger
            if triggered:
                game_events.info("AV detection on {network_id} caused {player_name} lost the computer.".format(network_id=x,
                    player_name=self.game.player_manager.name(self.network_state[x])))
                self.predicat_system[x].construct_random_system(GAME_PREDICAT_LEVEL)
                self.make_alive(x)
        game_events.info("Network randomization has ended.")

    def make_alive(self, index):
        self.state[index] = NetworkValueState.COMPUTER_ALIVE

    def random_computer(self):
        idx = random.randint(0, self.size - 1)
        return (idx, self.state[idx], self.predicat_system[idx])

    def __iter__(self):
        for idx, value in enumerate(self.state):
            with self.rlock:
                yield (value, self.predicat_system[idx])

class PlayerManager:

    def __init__(self, game):
        self.player_list = {}
        self.player_score = {}
        self.player_positions = {}
        self.players_online = {}

        self.game = game

    def score(self, player_id):
        assert self.exists(player_id)
        return self.player_score[player_id]

    def name(self, player_id):
        assert self.exists(player_id)
        return self.player_list[player_id]

    def exists(self, player_id):
        return player_id in self.player_list

    def connected(self, player_id):
        assert player_id in self.players_online
        return self.players_online[player_id]

    def mark_as_online(self, player_id):
        assert player_id in self.players_online
        self.players_online[player_id] = True

    def mark_as_disconnected(self, player_id):
        assert player_id in self.players_online
        self.players_online[player_id] = False

    def load_players(self, filename='player_database.data'):
        if not os.path.isfile(filename):
            game_events.critical("Player database is not set. The game cannot start!")
            raise Exception("Player database is not set. The game cannot start!")

        with open(filename, "r") as f:
            game_events.info("Loading player database file...")
            for line in f:
                player_id, player_name = map(str.strip, line.split(":"))
                player_id = int(player_id)

                self.player_list[player_id] = player_name
                self.player_score[player_id] = 0
                self.players_online[player_id] = False

                game_events.debug("{player_name} have id: {player_id}.".format(player_name=player_name, player_id=player_id))
            game_events.info("Player database loaded.")

    def add_score(self, player_id, value):
        assert player_id in self.player_score
        self.player_score[player_id] += value

    def add_player(self, player_name):
        new_id = random.randint(1, 2**16 - 1)
        while new_id in self.player_list:
            new_id = random.randint(1, 2**16 - 1)

        self.player_list[new_id] = player_name
        self.player_score[new_id] = 0

        game_events.info("Player {player_name} (id: {player_id}) has been successfully added in the system.".format(player_id=new_id, player_name=player_name))

        return new_id

    def del_player(self, player_id):
        if player_id in self.player_list:
            pos = self.player_positions[player_id]
            for i in pos:
                self.game.network.make_alive(i)

            del self.player_list[player_id]
            del self.player_score[player_id]
            del self.player_positions[player_id]
            game_events.info("Player {player_name} (id: {player_id}) has been successfully removed from system.".format(player_id=player_id, player_name=player_name))




class GameState:

    def __init__(self, rlock, network_size=2000, event_publisher_port=5488):
        game_events.info("Game state is initializing...")
        self.rlock = rlock

        self.network = Network(network_size, self, rlock)
        self.player_manager = PlayerManager(self)

        # Load players in the database
        self.player_manager.load_players()

        # Construct the network
        self.network.construct_random_network()

        self.event_publisher = context.socket(zmq.PUB)
        self.event_publisher.connect('tcp://127.0.0.1:{port}'.format(port=event_publisher_port))
        api_events.info("Event publisher is now running on tcp://127.0.0.1:{port}.".format(port=event_publisher_port))

        self.event_publisher.send("NETWORK_CONFIGURATION {net_size}".format(net_size=self.network.size))

        self.start_time = time.time()
        self.last_time = time.time()

        game_events.info("Game state ready. Start time is {start_time}.".format(start_time=self.start_time))

    def on_new_player_connected(self, player_id):
        player_name = self.player_manager.name(player_id)
        self.player_manager.mark_as_online(player_id)

        self.event_publisher.send("NEW_PLAYER {player_id} {player_name}".format(player_id=player_id, player_name=player_name))

    def on_player_disconnected(self, player_id):
        player_name = self.player_manager.name(player_id)
        self.player_manager.mark_as_disconnected(player_id)

        self.event_publisher.send("PLAYER_DISCONNECTION {player_id} {player_name}".format(player_id=player_id, player_name=player_name))

    def on_dispatch_infection(self, player_id, pattern):
        current_taken = self.player_manager.score(player_id)
        player_name = self.player_manager.name(player_id)

        # Got all computers, bitches
        if current_taken == self.network.size:
            game_events.info("{player_name} has all computers of the network. We don't need to dispatch his virus.".format(player_name=player_name))
            packet_max_computers_reached = struct.pack('!BI', ServerOpcode.MAXIMUM_INFECTION, current_taken)
            yield packet_max_computers_reached
            network_events.info("Maximum computers reached packet has been sent to {player_name}.".format(player_name=player_name))
            raise StopIteration

        game_events.info("{player_name} is dispatching his virus on the network...".format(player_name=player_name))
        game_events.info("{player_name} has currently {taken} computers on the network.".format(player_name=player_name,
            taken=current_taken))

        c_id, state, predicat = self.network.random_computer()

        result = predicat.eval_system(pattern)
        timestamp = self.last_time + 1
        if result:
            game_events.debug("{player_name} has infected computer (id: {computer_id}) with pattern {pattern_code} at {timest} seconds.".format(player_name=player_name,
                    computer_id=c_id, pattern_code=pattern, timest=(timestamp - self.start_time)))

            self.network.set_state(c_id, player_id)

            if state != NetworkValueState.COMPUTER_ALIVE and state != player_id:
                    self.player_manager.add_score(state, -1)
                    game_events.debug("{player_name_adv} has lost the computer id {computer_id} against {player_name}!".format(player_name=player_name,
                            computer_id=c_id, player_name_adv=self.player_manager.name(state)))

            if state != player_id:
                self.player_manager.add_score(player_id, 1)

            if self.player_manager.score(player_id) != current_taken:
                self.event_publisher.send("INFECTION_OCCURRED {player_id} {timestamp} {start_time} {score} {pattern} {net_size}".format(player_id=player_id,
                    timestamp=timestamp, start_time=self.start_time, score=self.player_manager.score(player_id),
                    pattern=pattern, net_size=self.network.size))
        else:
            game_events.debug("{player_name} has failed to infect computer (id: {computer_id}) with pattern {pattern_code}.".format(player_name=player_name,
                computer_id=c_id, pattern_code=pattern))

        self.last_time = timestamp
        game_events.info("Infection result for {player_name} is: infection {result} ".format(player_name=player_name, result=("SUCCESS" if result else "FAILED")))
        packet_result_infection = struct.pack('!BII', ServerOpcode.RESULT_INFECTION, current_taken, bool(result))
        network_events.debug("Infection packet result is going to be sent: {raw_data}".format(raw_data=repr(packet_result_infection)))
        yield packet_result_infection
        network_events.info("Infection packet result sent for {player_name}.".format(player_name=player_name))
        raise StopIteration



class VirusGameTCPHandler(SocketServer.BaseRequestHandler):

    def authenticate(self, player_id):
        with self.server.rlock:
            network_events.info("Player with id {player_id} is trying to authenticating himself on the server.".format(player_id=player_id))
            if not self.server.state.player_manager.exists(player_id):
                network_events.warning("This player doesn't exists in the database! Closing the connection.")
                self.request.close()
                return False
            if self.server.state.player_manager.connected(player_id):
                network_events.error("The player {player_name} is already connected! Hacking attempt!".format(player_name=self.server.state.player_manager.name(player_id)))
                self.request.close()
                return False

            self.player_name = self.server.state.player_manager.name(player_id)
            self.player_id = player_id
            network_events.info("Player with id {player_id} has been authenticated as {player_name}.".format(player_id=self.player_id,
                player_name=self.player_name))

            packet_auth_response = struct.pack('!BI', ServerOpcode.NETWORK_SIZE_ANNOUNCEMENT, self.server.state.network.size)
            self.request.sendall(packet_auth_response)

            return True

    def dispatch_infection(self, player_infection_pattern):
        for packet in self.server.state.on_dispatch_infection(self.player_id, player_infection_pattern):
            self.request.sendall(packet)

    def handle(self):
        network_events.debug("Connection received, a new client has spawn ({ip}:{port})!".format(ip=self.client_address[0], port=self.client_address[1]))
        Running = True
        Authenticated = False
        while Running:
            try:
                if not Authenticated:
                    network_events.debug("Data received from {ip}!".format(ip=self.client_address[0]))
                else:
                    network_events.debug("Data received from {player_name}!".format(player_name=self.player_name))

                opcode, = struct.unpack('!B', self.request.recv(1))
                if not Authenticated:
                    network_events.debug("Opcode decoded is {opcode_id} from {ip}!".format(opcode_id=opcode, ip=self.client_address[0]))
                else:
                    network_events.debug("Opcode decoded is {opcode_id} from {player_name}!".format(opcode_id=opcode, player_name=self.player_name))

                if opcode == ClientOpcode.AUTH:
                    player_id, = struct.unpack('!H', self.request.recv(2))
                    Authenticated = self.authenticate(player_id)

                    if not Authenticated:
                        network_events.info("{player_id}/{ip} has been refused and disconnected.".format(player_id=player_id, ip=self.client_address[0]))
                        Running = False
                    else:
                        network_events.info("{player_name} is now authenticated as {ip}.".format(player_name=self.player_name, ip=self.client_address[0]))
                        self.server.state.on_new_player_connected(player_id)

                elif opcode == ClientOpcode.INFECTION and Authenticated:
                    network_events.debug("Received infection opcode from {player_name}...".format(player_name=self.player_name))
                    player_infection_pattern, = map(str.strip, struct.unpack('!8s', self.request.recv(8)))
                    network_events.debug("{player_name} is trying to infect computers with pattern {pattern_code}.".format(player_name=self.player_name,
                        pattern_code=player_infection_pattern))
                    self.dispatch_infection(player_infection_pattern)
                elif opcode == ClientOpcode.INFECTION and not Authenticated:
                    network_events.error("Received infection opcode without authentication from {ip}... Disconnecting the client.".format(ip=self.client_address[0]))
                    self.request.close()
                    Running = False
                elif opcode == ClientOpcode.DISCONNECTION:
                    network_events.info("{player_name} has send the end opcode which means that he wants to disconnect.".format(player_name=self.player_name))
                    Running = False
                    self.server.state.on_player_disconnected(self.player_id)
            except Exception as e:
                if Authenticated:
                    network_events.exception("Player {player_name} (id: {player_id}) seems to have crashed.".format(player_name=self.player_name, player_id=self.player_id))
                    self.request.close()
                    self.server.state.on_player_disconnected(self.player_id)
                else:
                    network_events.exception("Player {ip} seems to have crashed.".format(ip=self.client_address[0]))
                    self.request.close()

                Running = False

            # self.timers += [Timer(2500, partial(GameState.randomize_network, self.server.state)), Timer(8600, partial(GameState.kill_viruses, self.server.state))]


def configure_logger(logger, filename, fmt, level, datefmt):
    stderr = StreamHandler()
    filehandler = FileHandler(filename)
    formatter = Formatter(fmt=fmt, datefmt=datefmt)

    logger.addHandler(stderr)
    logger.addHandler(filehandler)

    logger.setLevel(level)

    stderr.setFormatter(formatter)
    filehandler.setFormatter(formatter)


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 5481

    baseConfiguration = {}
    with open("config.conf", "r") as f:
        for line in f:
            if not line.startswith("#"):
                conf_data = line.split("=")
                if 'logging_level' in conf_data[0].lower():
                    numeric_value = getattr(logging, conf_data[1].upper().strip(), None)
                    if numeric_value is None:
                        raise Exception("Numeric value for logging ({key}) is invalid!".format(key=conf_data[0].lower()))
                    baseConfiguration[conf_data[0].lower().strip()] = numeric_value
                else:
                    baseConfiguration[conf_data[0].lower().strip()] = conf_data[1].lower().strip()
    basicFormat = "%(asctime)s - %(name)s - %(levelname)s : %(message)s"
    basicDateFmt = "%d/%m/%Y %H:%M:%S"

    try:
        configure_logger(game_events, 'game.log', basicFormat, baseConfiguration["game_events_logging_level"], basicDateFmt)
        configure_logger(network_events, 'network.log', basicFormat, baseConfiguration["network_events_logging_level"], basicDateFmt)
        configure_logger(api_events, 'api.log', basicFormat, baseConfiguration['api_events_logging_level'], basicDateFmt)
    except Exception as e:
        raise Exception("Failed to configure loggers, verify the configuration file (config.conf). The syntax may be broken or needed value absent.\nOriginal exception: {exc}".format(exc=repr(e)))

    rlock = RLock()

    game_events.info("Generating the game world state...")
    state = GameState(rlock)

    # Create the server, binding to all interfaces on port 5481
    server = SocketServer.ThreadingTCPServer((HOST, PORT), VirusGameTCPHandler)
    server.rlock = rlock
    server.state = state

    game_events.info("Configurating network system and game system...")
    network_events.info("Configurating network system and game system...")

    api_events.info("API is now ready to be use.")

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    network_events.info("Server is now listening on {host}:{port}.".format(host=HOST, port=PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        game_events.info("Game has ended.")
        network_events.info("Server has stopped to serve.")
        api_events.info("API is now disabled.")

    