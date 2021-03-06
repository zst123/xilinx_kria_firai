'''
Copyright 2021 Avnet Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

# USAGE
# python avnet_face_detection.py [--input 0] [--detthreshold 0.55] [--nmsthreshold 0.35]

from ctypes import *
from typing import List
import cv2
import numpy as np
import vart
import pathlib
import xir
import os
import math
import threading
import time
import sys
import argparse

from imutils.video import FPS

sys.path.append(os.path.abspath('../'))
sys.path.append(os.path.abspath('./'))
from vitis_ai_vart.facedetect import FaceDetect
from vitis_ai_vart.utils import get_child_subgraph_dpu


# construct the argument parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-i", "--input", required=False,
    help = "input camera identifier (default = 0)")
ap.add_argument("-d", "--detthreshold", required=False,
    help = "face detector softmax threshold (default = 0.55)")
ap.add_argument("-n", "--nmsthreshold", required=False,
    help = "face detector NMS threshold (default = 0.35)")
args = vars(ap.parse_args())

if not args.get("input",False):
    inputId = 0
else:
    inputId = int(args["input"])
print('[INFO] input camera identifier = ',inputId)

if not args.get("detthreshold",False):
    detThreshold = 0.55
else:
    detThreshold = float(args["detthreshold"])
print('[INFO] face detector - softmax threshold = ',detThreshold)

if not args.get("nmsthreshold",False):
    nmsThreshold = 0.35
else:
    nmsThreshold = float(args["nmsthreshold"])
print('[INFO] face detector - NMS threshold = ',nmsThreshold)

# Initialize Vitis-AI/DPU based face detector
densebox_xmodel = "/usr/share/vitis_ai_library/models/densebox_640_360/densebox_640_360.xmodel"
densebox_xmodel = "../dpu_yolov4/dpu_yolov4.xmodel"
densebox_graph = xir.Graph.deserialize(densebox_xmodel)
densebox_subgraphs = get_child_subgraph_dpu(densebox_graph)
assert len(densebox_subgraphs) == 1 # only one DPU kernel
densebox_dpu = vart.Runner.create_runner(densebox_subgraphs[0],"run")

class_names = ["fire",]
anchor_list = [12,16,19,36,40,28,36,75,76,55,72,146,142,110,192,243,459,401]
anchor_float = [float(x) for x in anchor_list]
anchors = np.array(anchor_float).reshape(-1, 2)
dpu_face_detector = FaceDetect(densebox_dpu,class_names,anchors,detThreshold,nmsThreshold)
dpu_face_detector.start()

# Initialize the camera input
print("[INFO] starting camera input ...")
cam = cv2.VideoCapture(inputId)
cam.set(cv2.CAP_PROP_FRAME_WIDTH,640)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
if not (cam.isOpened()):
        print("[ERROR] Failed to open camera ", inputId )
        exit()

# start the FPS counter
fps = FPS().start()

# loop over the frames from the video stream
while True:
    # Capture image from camera
    ret,frame = cam.read()
    
    # Camera provided BGR, and DPU needs RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    imgHeight = frame_rgb.shape[0]
    imgWidth  = frame_rgb.shape[1]

    # Vitis-AI/DPU based face detector
    boxes, scores, classes = dpu_face_detector.process(frame_rgb)

    # loop over the faces
    for _box, _score, _class_num in zip(boxes, scores, classes):
        _name = class_names[_class_num]
        _score = int(_score*100)
        top,left,bottom,right = _box.astype(int)
        box_height = bottom-top
        box_width = right-left
        
        # adjust box size
        adjustment = 0.2
        top    += int(adjustment*box_height)
        bottom -= int(adjustment*box_height)
        left   += int(adjustment*box_width)
        right  -= int(adjustment*box_width)     
        
        # draw a bounding box surrounding the object so we can
        color = (64, 64, 255)
        cv2.rectangle( frame, (left,top), (right,bottom), color, 4)
        cv2.putText(frame, f"{_score}% {_name}",
                    (left+8,bottom-8), cv2.FONT_HERSHEY_SIMPLEX, 
                    0.8, color, 2, cv2.LINE_AA)
    
    # Update the FPS counter
    fps.update()
    fps.stop()
    fps_count = fps.fps()
    color = (255, 255, 255)
    cv2.putText(frame, f"FPS: {fps_count:.2f}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 
                                        0.5, color, 2, cv2.LINE_AA)

    # Display the processed image
    cv2.imshow("Fire Detection", frame)
    key = cv2.waitKey(1) & 0xFF

    # if the `q` key was pressed, break from the loop
    if key == ord("q"):
        break

# Stop the timer and display FPS information
fps.stop()
print("[INFO] elapsed time: {:.2f}".format(fps.elapsed()))
print("[INFO] elapsed FPS: {:.2f}".format(fps.fps()))

# Stop the face detector
dpu_face_detector.stop()
del densebox_dpu

# Cleanup
cv2.destroyAllWindows()
