from threading import Thread
import time
import serial
import datetime
import random
import numpy as np
import cv2
from imutils.video import VideoStream 
import imutils

##### Settings for the user to change #####

#Device setup
serialPort = '/dev/ttyUSB0'
reverseD6T = True

##Writing intervals
# This is the waiting time between writing calls, in seconds
pLogFile = 1 # Interval between logfile writes
pCam = 10 # Interval between camera picture saving and detecting

#Detection parameters
TargetDev = 1.8 # This is the deviation that should trigger a human presence alert
TargetTolerance = 1 # This is the tolerance for when the current value drops below the registered value

TargetTemp = 18 # Temperature to consider a human, above this we will consider it a person

#Camera detection configuration
yolov3_classes = "yolov3.txt"
yolov3_config = "yolov3-tiny.cfg"
yolov3_weights = "yolov3-tiny.weights"

## os.path.split(sys.argv[0])[0] will retrieve the directory the script is running from, accurately
## this seems to be an issue on Linux however, where just the filename works

#CSV file writing
filePath = "/var/www/html/logfile.csv" # Full file path, properly escaped
filePathDetail = "/var/www/html/logfile-detail.csv" # Full file path, properly escaped

# !!! Make sure the script has permissions to write to these folders !!!

#Functionality setup
debug = False # If this is enabled the script will output the values being read to the console
csv_on = True
cam_on = True
cam_mode = "pi" # "usb" to use a USB camera, "pi" to use Pi's camera

### Excel does not meet the csv standards. To correctly import in Excel either:
## 1. Add SEP=, in the first line (not required for other softwares, will appear as a value in other softwares)
## 2. Change the extension to .txt and run the Text Importing Assistant

##### End of Settings #####
valsDetail = [0] * 8
dhLastSensorVals = [[0,0,0]]
for i in range(7):
        dhLastSensorVals.append([0,0,0])
dhLastSensorValsWrites = 0
dhPresence = [0,0,0,0,0,0,0,0]
dhPresenceTemp = [0,0,0,0,0,0,0,0]
camBoundariesX = ((0,50),(50,100),(100,150),(150,200),(200,250),(250,300),(300,350),(350,400))
camBoundariesY = (0,300)
dhCamPresence = [0,0,0,0,0,0,0,0]
valPTAT = 0
connected = False
notKill = True

class DetectHuman():
        def updateCelVals(self, argCel, argVal):
                global dhLastSensorValsWrites
                dhLastSensorVals[argCel].pop(0)
                dhLastSensorVals[argCel].append(argVal)
                if dhLastSensorValsWrites <=25:
                        dhLastSensorValsWrites += 1

        def checkHuman(self, argCell):
                global dhLastSensorValsWrites
                global TargetTemp
                if dhLastSensorValsWrites>20: #we're discarding more values as there seems to be some delay starting the sensor
                        isPerson = False
                        if int(dhLastSensorVals[argCell][2])>TargetTemp:
                                isPerson = True
                        if isPerson:
                                dhPresence[argCell] = 1
                        else:
                                dhPresence[argCell] = 0

        def checkEntranceCell(self, argCel):
                global dhLastSensorValsWrites
                if dhLastSensorValsWrites>20: #we're discarding more values as there seems to be some delay starting the sensor
                        dev = self.calcHDifToLastVal(dhLastSensorVals[argCel])
                        isPerson = False
                        if dev > TargetDev:
                                isPerson = True
                        if isPerson:
                                dhPresence[argCel] = 1
                                dhPresenceTemp[argCel] = dhLastSensorVals[argCel][len(dhLastSensorVals[argCel])-1]
                                self.normaliseCellVals(argCel)

        def checkExitCell(self, argCel):
                global dhLastSensorValsWrites
                if dhLastSensorValsWrites>20 and dhPresence[argCel] == 1:
                        dev = self.calcHDifToLastVal(dhLastSensorVals[argCel], True)
                        isPerson = True
                        if dev < (TargetDev*-1):
                                isPerson = False
                        if isPerson == False:
                                dhPresence[argCel] = 0
                                self.normaliseCellVals(argCel)

        def checkPresence(self, argCel):
                global dhLastSensorValsWrites
                if dhLastSensorValsWrites>20 and dhPresence[argCel] == 1 and \
                int(dhLastSensorVals[argCel][len(dhLastSensorVals[argCel])-1]) < int(dhPresenceTemp[argCel]) - TargetTolerance:
                                dhPresence[argCel] = 0

        def normaliseCellVals(self, argCel):
                val = dhLastSensorVals[argCel][2]
                dhLastSensorVals[argCel][0] = val
                dhLastSensorVals[argCel][1] = val

        def calcHDifToLastVal(self, arg, negative=False):
                dif = [0] * (len(arg) - 1)
                for d in range(len(arg)-1):
                        dif[d] = int(arg[len(arg)-1])-int(arg[d])
                result = 0
                if negative:
                        result = min(dif)
                else:
                        result = max(dif)
                return result

        def checkBoundary(self, argX, argY):
                inside = False
                box = -1

                for x in range(8):
                        if camBoundariesX[x][0]<=argX<=camBoundariesX[x][1] and camBoundariesY[0]<=argY<=camBoundariesY[1]:
                                inside = True
                                box = x
                                break
                
                return (inside, box)

class DataProcessing():
        def addToFile(self, filepath, txt):
                F = open(filepath, 'a')
                F.write(txt)
        
        def buildCsvString(self, time, values):
                finalString = time + ','
                for x in range(len(values)):
                        if x < len(values)-1:
                                finalString += str(values[x]) + ','
                        else:
                                finalString += str(values[x])
                finalString += '\n'
                return finalString

class CameraDetection():
        colours = None
        classes = None

        def main(self):
                global yolov3_classes
                global yolov3_weights
                global yolov3_config
                global pCam
                global dhCamPresence

                vs = None
                if cam_mode == "pi":
                        vs = VideoStream(usePiCamera=True).start()
                elif cam_mode == "usb":
                        vs = VideoStream(src=0).start()
                else:
                        print("Camera mode is not properly setup")
                        exit()
                
                time.sleep(2.0) #Delay for camera VideoStream to start

                #Setting up the classes
                with open(yolov3_classes, 'r') as f:
                        self.classes = [line.strip() for line in f.readlines()]

                #Setting up the colours
                self.colours = np.random.uniform(0, 255, size=(len(self.classes), 3))

                #Loading the model
                net = cv2.dnn.readNet(yolov3_weights, yolov3_config)

                global notKill
                while notKill:
                        ts = time.time()
                        st = datetime.datetime.fromtimestamp(ts).strftime('%Y%m%d_%H%M%S')

                        # grab the frame from the threaded video stream and resize it
                        # to have a maximum width of 400 pixels
                        frame = vs.read()
                        frame = imutils.resize(frame, width=400,inter=cv2.INTER_CUBIC)
                
                        # grab the frame dimensions and convert it to a blob
                        Height, Width = frame.shape[:2]
                        #blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)),
                        #        0.007843, (300, 300), 127.5)
                        blob = cv2.dnn.blobFromImage(frame, 0.00392, (416,416), (0,0,0), True, crop=False)
                
                        # pass the blob through the network and obtain the detections and
                        # predictions
                        net.setInput(blob)

                        outs = net.forward(self.get_output_layers(net))

                        class_ids = []
                        confidences = []
                        boxes = []
                        conf_threshold = 0.5
                        nms_threshold = 0.4
                        camPeople = 0
                        dhCamPresence = [0,0,0,0,0,0,0,0]

                        for out in outs:
                                for detection in out:
                                        scores = detection[5:]
                                        class_id = np.argmax(scores)
                                        confidence = scores[class_id]
                                        if confidence > 0.5 and self.classes[class_id] == "person": #need to further develop from here
                                                center_x = int(detection[0] * Width)# we can use these centers to know where the person is
                                                center_y = int(detection[1] * Height)# then we can send it to the checkboundaries
                                                print(str(center_x) + "w " + str(center_y) + "h")
                                                isInside, place = DetectHuman().checkBoundary(center_x,center_y)
                                                
                                                if isInside:
                                                        dhCamPresence[place] = 1
                                                        camPeople += 1
                                                print(dhCamPresence)
                                                print(place)
                                                w = int(detection[2] * Width)
                                                h = int(detection[3] * Height)
                                                x = center_x - w / 2
                                                y = center_y - h / 2
                                                class_ids.append(class_id)
                                                confidences.append(float(confidence))
                                                boxes.append([x, y, w, h])

                        indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold)

                        for i in indices:
                                i = i[0]
                                box = boxes[i]
                                x = box[0]
                                y = box[1]
                                w = box[2]
                                h = box[3]
                                self.draw_prediction(frame, class_ids[i], confidences[i], round(x), round(y), round(x+w), round(y+h))
                                
                        imageName = st + '_' + str(camPeople)  + 'p.jpg'
                        print(imageName)
                        cv2.imwrite(imageName, frame)
                        #cv2.destroyAllWindows() #Need?

                        time.sleep(pCam)

        def get_output_layers(self, net):
                layer_names = net.getLayerNames()
                output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]

                return output_layers
        
        def draw_prediction(self, img, class_id, confidence, x, y, x_plus_w, y_plus_h):
                label = str(self.classes[class_id])
                colour = self.colours[class_id]
                cv2.rectangle(img, (x,y), (x_plus_w,y_plus_h), colour, 2)
                cv2.putText(img, label, (x-10,y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 2)


## Thread classes
class SerialThread(Thread):
 
    def __init__(self):
        Thread.__init__(self)
        
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

        global notKill
        while notKill:
                global valPTAT
                ler = conn.readline().decode()
                ler = ler.strip()
                temp = ler.split(",")
                for i in range(8):
                        valsDetail[i] = temp[i]
                if(reverseD6T):
                        valsDetail.reverse()
                valPTAT = temp[8]

                global connected
                connected = True
            
                if debug:
                    print("Values: {}".format(valsDetail))
                    print("PTAT Value: {}".format(valPTAT))
        conn.close()


class DataThread(Thread):
 
    def __init__(self):
        Thread.__init__(self)
        
    def run(self):
        global notKill
        while notKill:
                ts = time.time()
                st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d,%H:%M:%S')
                day = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

                global dhCamPresence
                
                allPresence = [0,0,0,0,0,0,0,0]
                for x in range(8):
                        if dhPresence[x] == 1:
                                allPresence[x] += 1
                        if dhCamPresence[x] == 1:
                                allPresence[x] += 2
                
                print(allPresence)
                printVals = []
                printVals.extend(valsDetail)
                printVals.append(valPTAT)
                stringPrintDetail = DataProcessing().buildCsvString(st, printVals)
                stringPrintNormal = DataProcessing().buildCsvString(st, allPresence)

                fpDetFinal = filePathDetail[:-4] + day + ".csv"
                fpFinal = filePath[:-4] + day + ".csv"

                #Writing the new line in the file
                if csv_on:
                        DataProcessing().addToFile(fpDetFinal, stringPrintDetail)
                        DataProcessing().addToFile(fpFinal, stringPrintNormal)

                ## Add this all to the same file?
                ## Need a way to process this into the table as a annotation

                #Waiting for the interval so we don't write too fast
                time.sleep(pLogFile)

class DetectHumanThread(Thread):
        def __init__(self):
                Thread.__init__(self)
        
        def run(self):
                global notKill
                while notKill:
                        for i in range(8):
                                DetectHuman().updateCelVals(i, valsDetail[i])
                                DetectHuman().checkHuman(i)
                                #DetectHuman().checkEntranceCell(i)
                                #DetectHuman().checkExitCell(i)
                                #DetectHuman().checkPresence(i)
                                
                        time.sleep(pLogFile)

class CameraThread(Thread):
        def __init__(self):
                Thread.__init__(self)
        
        def run(self):
                CameraDetection().main()

## Main routine
if __name__ == '__main__':
        thread1 = SerialThread()
        thread1.setName('Thread 1')
        thread1.start()
        
        while True:
                if connected:
                        thread2 = DataThread()
                        thread2.setName('Thread 2')

                        thread3 = DetectHumanThread()
                        thread3.setName('Thread 3')

                        thread2.start()
                        thread3.start()

                        if cam_on:
                                thread4 = CameraThread()
                                thread4.setName('Thread 4')
                                thread4.start()
                        
                        break

        #Locking mainthread while thread1 is still alive
        #This means the program won't terminate until thread1 crashes or
        #until we catch the KeyboardInterrupt that will signal
        #every thread to kill itself correctly
        try:
                while(thread1.is_alive):
                        time.sleep(1)        
        except KeyboardInterrupt:
                print("Stopping every task")
                notKill=False

        print('Program closing')
