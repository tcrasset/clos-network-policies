from threading import Timer,Thread,Event


class Timer(Thread):
    def __init__(self, event, function, interval=1):
        Thread.__init__(self, function)
        self.stopped = event
        self.function = function
        self.interval = interval

    def run(self):
        while not self.stopped.wait(self.interval):
            self.function()
            print("Mythread")