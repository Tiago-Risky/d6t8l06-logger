# D6T8L06

This application will log the values read from the D6T8L06, attempt to detect people, and export the values and results to a CSV or through the Google API to the cloud. It can also detect people using a Camera (usb or Pi camera), which we are using as a test/control measure for development.

This is still a work-in-progress application.

## Dependencies to be installed

Here's how to solve all your Python dependencies for this project:

    python3 -m pip install -r requirements.txt

## Google IoT Core source

My Google IoT Core MQTT code is based on https://github.com/GoogleCloudPlatform/python-docs-samples/blob/master/iot/api-client/mqtt_example/cloudiot_mqtt_example.py

Many thanks to developers behind Google Cloud Platform (https://github.com/GoogleCloudPlatform) for their example code.

## OpenCV source

My OpenCV code is based on https://github.com/arunponnusamy/object-detection-opencv

You can get the yolov3.weights, yolov3.txt and yolov3.cfg files from that project. Unfortunately I can't upload the yolov3.weights on my own project due to filesize limits on my account.

Many thanks to Arun Ponnusamy (https://github.com/arunponnusamy/) for his example code.