from threading import Thread
import time
import serial
import datetime
import os
import sys
import random
import ssl
import jwt
import paho.mqtt.client as mqtt
import numpy as np
import cv2
from imutils.video import VideoStream 
import imutils

##### Settings for the user to change #####

#Device setup
serialPort = '/dev/ttyUSB0'

##Writing intervals
# This is the waiting time between writing calls, in seconds
pLogFile = 1 # Interval between logfile writes
pMQTT = 12 # Interval between MQTT telemetry reports ()
pCam = 6 # Interval between camera picture saving and detecting

#Detection parameters
TargetDev = 1.8 # This is the deviation that should trigger a human presence alert
TargetTolerance = 1 # This is the tolerance for when the current value drops below the registered value

#Camera detection configuration
yolov3_classes = "yolov3.txt"
yolov3_config = "yolov3.cfg"
yolov3_weights = "yolov3.weights"

## os.path.split(sys.argv[0])[0] will retrieve the directory the script is running from, accurately
## this seems to be an issue on Linux however, where just the filename works

#CSV file writing
filePath = "/var/www/html/logfile.csv" # Full file path, properly escaped
filePathDetail = "/var/www/html/logfile-detail.csv" # Full file path, properly escaped

#Functionality setup
debug = False # If this is enabled the script will output the values being read to the console
mode = "full-detail" # Check "Modes" for details
mqtt_on = False
csv_on = True
cam_on = False
cam_mode = "usb" # "usb" to use a USB camera, "pi" to use Pi's camera

## Modes
# "full-detail" mode
# This means both the Detail and Normal .csv files are outputted and the MQTT telemetry will be Detail only

# "mqtt-normal" mode
# This mode will output mqtt in Normal level, however it will output both Detail and Normal level .csv files

# "full-normal" mode
# This mode will output both the MQTT telemetry and the .csv file in Normal level only.

## Levels of information detail
# "Normal" level means only mean temperature and nr of people is outputted.
# "Detail" level means the temperature for each sensor cell is outputted.

# !!! Make sure the script has permissions to write in the folder !!!


### Excel does not meet the csv standards. To correctly import in Excel either:
## 1. Add SEP=, in the first line (not required for other softwares, will appear as a value in other softwares)
## 2. Change the extension to .txt and run the Text Importing Assistant

##### End of Settings #####
buffer = True if (pLogFile != pMQTT) else False
valsDetail = [0] * 8
dhLastSensorVals = [[0,0,0]]
for i in range(7):
        dhLastSensorVals.append([0,0,0])
dhLastSensorValsWrites = 0
dhPresence = [0,0,0,0,0,0,0,0]
dhPresenceTemp = [0,0,0,0,0,0,0,0]
camBoundariesX = ((0,1),(2,3),(4,5),(6,7),(8,9),(10,11),(12,13),(14,15))
camBoundariesY = (0,1)
dhCamPresence = [0,0,0,0,0,0,0,0]
bufferList = []
valPTAT = 0
connected = False
notKill = True

class GCloudIOT():
        # The initial backoff time after a disconnection occurs, in seconds.
        minimum_backoff_time = 1

        # The maximum backoff time before giving up, in seconds.
        MAXIMUM_BACKOFF_TIME = 32

        # Whether to wait with exponential backoff before publishing.
        should_backoff = False

        # Configuration
        arg_project_id = 'iot-test-0001' #GCP Cloud Project ID
        arg_registry_id = 'test-iot' #Cloud IoT Core registry NAME
        arg_device_id = 'device-python' #Cloud IoT Core device NAME
        arg_private_key_file = 'C:\\Users\\Tiago Cabral\\Desktop\\mqtt_python_test\\rsa_private.pem' #Path to private key file
        arg_algorithm = 'RS256' #Encryption to generate JWT, RS256 or ES256 available
        arg_cloud_region = 'europe-west1' #GCP Cloud Region
        arg_ca_certs = 'C:\\Users\\Tiago Cabral\\Desktop\\mqtt_python_test\\roots.pem' #Path to CA root obtained from https://pki.google.com/roots.pem
        arg_message_type = 'event' #Event (telemetry) or State(device state)
        arg_mqtt_bridge_hostname = 'mqtt.googleapis.com' #MQTT bridge hostname
        arg_mqtt_bridge_port = 8883 #MQTT bridge port, 8883 or 443 recommended
        arg_jwt_expires_minutes = 20 #Expiration time, in minutes, for JWT tokens

        # [START iot_mqtt_jwt]
        def create_jwt(self, project_id, private_key_file, algorithm):

                token = {
                        # The time that the token was issued at
                        'iat': datetime.datetime.utcnow(),
                        # The time the token expires.
                        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
                        # The audience field should always be set to the GCP project id.
                        'aud': project_id
                }

                # Read the private key file.
                with open(private_key_file, 'r') as f:
                        private_key = f.read()

                print('Creating JWT using {} from private key file {}'.format(
                algorithm, private_key_file))

                return jwt.encode(token, private_key, algorithm=algorithm)
        # [END iot_mqtt_jwt]


        # [START iot_mqtt_config]
        def error_str(self, rc):
                """Convert a Paho error to a human readable string."""
                return '{}: {}'.format(rc, mqtt.error_string(rc))


        def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
                """Callback for when a device connects."""
                print('on_connect', mqtt.connack_string(rc))

        # After a successful connect, reset backoff time and stop backing off.
                self.should_backoff = False
                self.minimum_backoff_time = 1


        def on_disconnect(self, unused_client, unused_userdata, rc):
                """Paho callback for when a device disconnects."""
                print('on_disconnect', self.error_str(rc))

                # Since a disconnect occurred, the next loop iteration will wait with
                # exponential backoff.
                self.should_backoff = True


        def on_publish(self, unused_client, unused_userdata, unused_mid):
                """Paho callback when a message is sent to the broker."""
                print('on_publish')


        def on_message(self, unused_client, unused_userdata, message):
                """Callback when the device receives a message on a subscription."""
                payload = str(message.payload)
                print('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
                payload, message.topic, str(message.qos)))


        def get_client(self,
                project_id, cloud_region, registry_id, device_id, private_key_file,
                algorithm, ca_certs, mqtt_bridge_hostname, mqtt_bridge_port):
                """Create our MQTT client. The client_id is a unique string that identifies
                this device. For Google Cloud IoT Core, it must be in the format below."""
                client = mqtt.Client(
                        client_id=('projects/{}/locations/{}/registries/{}/devices/{}'
                                .format(
                                project_id,
                                cloud_region,
                                registry_id,
                                device_id)))

                # With Google Cloud IoT Core, the username field is ignored, and the
                # password field is used to transmit a JWT to authorize the device.
                client.username_pw_set(
                        username='unused',
                        password=self.create_jwt(
                        project_id, private_key_file, algorithm))

                # Enable SSL/TLS support.
                client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)

                # Register message callbacks. https://eclipse.org/paho/clients/python/docs/
                # describes additional callbacks that Paho supports. In this example, the
                # callbacks just print to standard out.
                client.on_connect = self.on_connect
                client.on_publish = self.on_publish
                client.on_disconnect = self.on_disconnect
                client.on_message = self.on_message

                # Connect to the Google MQTT bridge.
                client.connect(mqtt_bridge_hostname, mqtt_bridge_port)

                # This is the topic that the device will receive configuration updates on.
                mqtt_config_topic = '/devices/{}/config'.format(device_id)

                # Subscribe to the config topic.
                client.subscribe(mqtt_config_topic, qos=1)

                return client
        # [END iot_mqtt_config]


        # [START iot_mqtt_run]
        def main(self):

                global pMQTT

                # Publish to the events or state topic based on the flag.
                sub_topic = 'events' if self.arg_message_type == 'event' else 'state'

                mqtt_topic = '/devices/{}/{}'.format(self.arg_device_id, sub_topic)

                jwt_iat = datetime.datetime.utcnow()
                jwt_exp_mins = self.arg_jwt_expires_minutes
                client = self.get_client(
                        self.arg_project_id, self.arg_cloud_region, self.arg_registry_id, self.arg_device_id,
                        self.arg_private_key_file, self.arg_algorithm, self.arg_ca_certs,
                        self.arg_mqtt_bridge_hostname, self.arg_mqtt_bridge_port)

                # Publish mesages to the MQTT bridge.
                global notKill
                while(notKill):
                        # Process network events.
                        client.loop()

                        # Wait if backoff is required.
                        if self.should_backoff:
                        # If backoff time is too large, give up.
                                if self.minimum_backoff_time > self.MAXIMUM_BACKOFF_TIME:
                                        print('Exceeded maximum backoff time. Giving up.')
                                        break

                        # Otherwise, wait and connect again.
                                delay = self.minimum_backoff_time + random.randint(0, 1000) / 1000.0
                                print('Waiting for {} before reconnecting.'.format(delay))
                                time.sleep(delay)
                                self.minimum_backoff_time *= 2
                                client.connect(self.arg_mqtt_bridge_hostname, self.arg_mqtt_bridge_port)

                        #Processing the buffer into our JSON object format
                        if (len(bufferList)>=(pMQTT-1)):
                                
                                payload = DataProcessing().buildPayload()

                                print('Publishing message: \'{}\''.format(payload))
                                # [START iot_mqtt_jwt_refresh]
                                seconds_since_issue = (datetime.datetime.utcnow() - jwt_iat).seconds
                                if seconds_since_issue > 60 * jwt_exp_mins:
                                        print('Refreshing token after {}s').format(seconds_since_issue)
                                        jwt_iat = datetime.datetime.utcnow()
                                        client = self.get_client(
                                                self.arg_project_id, self.arg_cloud_region,
                                                self.arg_registry_id, self.arg_device_id, self.arg_private_key_file,
                                                self.arg_algorithm, self.arg_ca_certs, self.arg_mqtt_bridge_hostname,
                                                self.arg_mqtt_bridge_port)
                                # [END iot_mqtt_jwt_refresh]
                                # Publish "payload" to the MQTT topic. qos=1 means at least once
                                # delivery. Cloud IoT Core also supports qos=0 for at most once
                                # delivery.
                                client.publish(mqtt_topic, payload, qos=1)
                                bufferList.clear() # This is not supported on older Python versions, only 3.3+
                        else:
                                #This is in case it's out of sync, we wait 1 second so it possibly fixes the issue
                                time.sleep(1)
                                continue
                        
                        # We're publishing the buffer 5 times per minute, to save on queries.
                        time.sleep(pMQTT)

                print('Finished.')
        # [END iot_mqtt_run]

class DetectHuman():
        def updateCelVals(self, argCel, argVal):
                global dhLastSensorValsWrites
                dhLastSensorVals[argCel].pop(0)
                dhLastSensorVals[argCel].append(argVal)
                if dhLastSensorValsWrites <=25:
                        dhLastSensorValsWrites += 1

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

                for x in range(len(camBoundariesX)):
                        if camBoundariesX[x][0]<=argX<=camBoundariesX[x][1] and camBoundariesY[0]<=argY<=camBoundariesY[1]:
                                inside = True
                                box = x
                
                return (inside, box)

class DataProcessing():
        def addToFile(self, filepath, txt):
                F = open(filepath, 'a')
                F.write(txt)

        def addToBuffer(self, time, value):
                global bufferList
                bufferVal = []
                bufferVal.extend(value)
                bufferVal.append(time)
                bufferList.append(bufferVal)
        
        def buildCsvString(self, time, values):
                finalString = time + ','
                for x in range(len(values)):
                        if x < len(values)-1:
                                finalString += str(values[x]) + ','
                        else:
                                finalString += str(values[x])
                finalString += '\n'
                return finalString

        def buildPayload(self):
                payload = ''
                if mode == "full-detail":
                        for x in range(len(bufferList)):
                                row = '{'
                                for y in range(8):
                                        row = row + '"s'+str(y+1)+'":"'+str(bufferList[x][y])+'",'
                                row = row + '"time":"' + str(bufferList[x][8]) + '"}'
                                if (x<len(bufferList)-1):
                                        row = row + ';'
                                payload = payload + row
                else:
                        for x in range(len(bufferList)):
                                row = '{"m":"'+str(bufferList[x][0])+'","p":"'+str(bufferList[x][1])+'","t":"'+str(bufferList[x][2])+'"}'
                                if (x<len(bufferList)-1):
                                        row = row + ';'
                                payload = payload + row
                return payload

class CameraDetection():
        colours = None
        classes = None

        def main(self):
                global yolov3_classes
                global yolov3_weights
                global yolov3_config
                global pCam

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
                        frame = imutils.resize(frame, width=400)
                
                        # grab the frame dimensions and convert it to a blob
                        Height, Width = frame.shape[:2]
                        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)),
                                0.007843, (300, 300), 127.5)
                
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
                                                isInside, place = DetectHuman().checkBoundary(center_x,center_y)
                                                if isInside:
                                                        dhCamPresence[place] = 1
                                                        camPeople += 1
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
                        cv2.imwrite(imageName, frame)
                        cv2.destroyAllWindows() #Need?

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
                
                valPTAT = temp[8]

                global connected
                connected = True
            
                if debug:
                    print("Values: {}".format(valsDetail))
                    print("PTAT Value: {}".format(valPTAT))



class DataThread(Thread):
 
    def __init__(self):
        Thread.__init__(self)
        
    def run(self):
        global notKill
        while notKill:
            if valsDetail:
                ts = time.time()
                st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d,%H:%M:%S')
                
                allPresence = [0,0,0,0,0,0,0,0]
                for x in range(8):
                        if dhPresence[x] == 1:
                                allPresence[x] += 1
                        if dhCamPresence[x] == 1:
                                allPresence[x] += 2               
                
                #Writing the new data to the Buffer
                global buffer
                if buffer:
                        if mode == "full-detail":
                                DataProcessing().addToBuffer(st, valsDetail)
                        else:
                                DataProcessing().addToBuffer(st, allPresence)

                printVals = []
                printVals.extend(valsDetail)
                printVals.append(valPTAT)
                stringPrintDetail = DataProcessing().buildCsvString(st, printVals)
                stringPrintNormal = DataProcessing().buildCsvString(st, allPresence)

                #Writing the new line in the file
                if csv_on:
                        if mode != "full-normal":
                                DataProcessing().addToFile(filePathDetail, stringPrintDetail)
                        DataProcessing().addToFile(filePath, stringPrintNormal)

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
                        global connected
                        if connected:
                                global TargetDev
                                
                                ## New per-cell detection
                                for i in range(8):
                                        DetectHuman().updateCelVals(i, valsDetail[i])
                                        DetectHuman().checkEntranceCell(i)
                                        #DetectHuman().checkExitCell(i)
                                        DetectHuman().checkPresence(i)
                                        ## checkExitCell can be replaced with checkPresence
                                        ## once checkPresence is fully functional and tested
                                        ## (need to check accuracy and need to add a margin of error)
                                print(dhLastSensorVals)
                                print(dhPresence)
                                ##

                                time.sleep(pLogFile)

class GCPThread(Thread):
        def __init__(self):
                Thread.__init__(self)
        
        def run(self):
                GCloudIOT().main()


class CameraThread(Thread):
        def __init__(self):
                Thread.__init__(self)
        
        def run(self):
                CameraDetection().main()

## Main routine
if __name__ == '__main__':
        thread1 = SerialThread()
        thread1.setName('Thread 1')
        
        thread2 = DataThread()
        thread2.setName('Thread 2')

        thread3 = DetectHumanThread()
        thread3.setName('Thread 3')

        thread1.start()
        thread2.start()
        thread3.start()

        if cam_on:
                thread4 = CameraThread()
                thread4.setName('Thread 4')
                thread4.start()

        if mqtt_on:
                thread5 = GCPThread()
                thread5.setName('Thread 5')
                thread5.start()
        
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
