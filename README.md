A game simulation of biologic virus infection of a human (computer)
===================================================================
It worked on a client/server topology with a little bit of ZeroMQ for events.
A client generate a random genetic code, the server create a network, which will generate random predicats, the client will try to match these predicats.

If it succeed, the network "computer" is now infected by the client.
If it fails, let's try another code with another computer.

The goal is to infect all computers, and become the MASTER VIRUS which has devasted humanity- wait what.

Well, it has been made for a trial (I know that it isn't one but it's a lot more cool when I say it like that), called TPE !
Which stands in French for "TRAVAUX PRATIQUES ENCADRES", my subject is AI (Artificial Intelligence).
And I just wanted to try to copy biological virus behaviour and simulate on computer.

The code contains a website which show a realtime chart of infection over time.

ALL IS LICENCED UNDER GPLv3.
