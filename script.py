from threading import Thread
import time
import serial
import datetime

# Settings for the user to change
serialPort = 'COM3'
frequency = 60 # Number of entry records per minute (at equal intervals)
filePath = "C:\\Users\\Tiago Cabral\\Desktop\\logfile.csv" # Full file path, properly escaped 
# Make sure the script has permissions to write in the folder!


### Excel does not meet the csv standards. To correctly import in Excel either:
## Add SEP=, in the first line (not required for other softwares, will appear as a value in other softwares)
## Change the extension to .txt and run the Text Importing Assistant

# End of Settings

frc = 1/(frequency / 60)
vals = [] * 8
valPTAT = 0
debug = True

class SerialThread(Thread):
 
    def __init__(self, val):
        Thread.__init__(self)
        self.val = val
        
    def run(self):
        while True:
            print("Attempting to connect")
            try:
                global serialPort
                conn = serial.Serial(serialPort, 9600)
                break
            except serial.SerialException as e:
                print("Fail to connect: {}".format(e))
                time.sleep(3)
        time.sleep(2)

        print("Listening")

        global vals

        while True:
            if not vals:
                vals = [0]*8
            else:
                global valPTAT
                ler = conn.readline().decode()
                ler = ler.strip()
                temp = ler.split(",")
                for i in range(8):
                    vals[i] = temp[i]

                valPTAT = temp[8]

                if debug:
                    print("Values: {}".format(vals))
                    print("PTAT Value: {}".format(valPTAT))



class WindowThread(Thread):
 
    def __init__(self, val):
        Thread.__init__(self)
        self.val = val
        
    def run(self):
        while(True):
            if vals:
                ts = time.time()
                st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d,%H:%M:%S')
                print(st)
                F = open(filePath, 'a')
                stringPrint = st + ','
                for x in vals:
                    stringPrint = stringPrint + x + ','
                stringPrint = stringPrint + valPTAT + '\n'

                F.write(stringPrint)
                time.sleep(frc)



if __name__ == '__main__':
    thread1 = SerialThread(1)
    thread1.setName('Thread 1')
 
    thread2 = WindowThread(2)
    thread2.setName('Thread 2')
    thread1.start()
    thread2.start()
 
    thread1.join()
    thread2.join()
 
    print('Main Terminating...')