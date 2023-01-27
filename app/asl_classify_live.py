'''
Copyright 2023 Avnet Inc.
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
#
# ASL Classification (live with USB camera)
#
# References:
#   https://www.github.com/AlbertaBeef/asl_tutorial.git
#
# Dependencies:
#


import numpy as np
import cv2
import os
from datetime import datetime
import itertools

#import keras
#from keras.models import load_model
#from keras.utils import to_categorical

from ctypes import *
from typing import List
import xir
import pathlib
import vart
#import threading
import time
import sys
import argparse
import glob
import subprocess
import re

def get_media_dev_by_name(src):
    devices = glob.glob("/dev/media*")
    for dev in sorted(devices):
        proc = subprocess.run(['media-ctl','-d',dev,'-p'], capture_output=True, encoding='utf8')
        for line in proc.stdout.splitlines():
            if src in line:
                return dev

def get_video_dev_by_name(src):
    devices = glob.glob("/dev/video*")
    for dev in sorted(devices):
        proc = subprocess.run(['v4l2-ctl','-d',dev,'-D'], capture_output=True, encoding='utf8')
        for line in proc.stdout.splitlines():
            if src in line:
                return dev

# ...work in progress ...
#def detect_dpu_architecture():
#    proc = subprocess.run(['xdputil','query'], capture_output=True, encoding='utf8')
#    for line in proc.stdout.splitlines():
#        if 'DPU Arch' in line:
#            #                 "DPU Arch":"DPUCZDX8G_ISA0_B128_01000020E2012208",
#            #dpu_arch = re.search('DPUCZDX8G_ISA0_(.+?)_', line).group(1)  
#            #                 "DPU Arch":"DPUCZDX8G_ISA1_B2304",
#            #dpu_arch = re.search('DPUCZDX8G_ISA1_(.+?)', line).group(1)
#            return dpu_arch

# Parameters (tweaked for video)
scale = 1.0
text_fontType = cv2.FONT_HERSHEY_SIMPLEX
text_fontSize = 0.75*scale
text_color    = (0,0,255)
text_lineSize = max( 1, int(2*scale) )
text_lineType = cv2.LINE_AA

print("[INFO] Searching for USB camera ...")
dev_video = get_video_dev_by_name("uvcvideo")
dev_media = get_media_dev_by_name("uvcvideo")
print(dev_video)
print(dev_media)

#input_video = 0 
input_video = dev_video  
print("[INFO] Input Video : ",input_video)

output_dir = './captured-images'

if not os.path.exists(output_dir):      
    os.mkdir(output_dir)            # Create the output directory if it doesn't already exist

cv2.namedWindow('ASL Classification')


# Open video
cap = cv2.VideoCapture(input_video)
frame_width = 640
frame_height = 480
cap.set(cv2.CAP_PROP_FRAME_WIDTH,frame_width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT,frame_height)
#frame_width = int(round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
#frame_height = int(round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
print("camera",input_video," (",frame_width,",",frame_height,")")

# Open ASL model
#model = load_model('tf2_asl_classifier_1.h5')

# Vitis-AI implementation of ASL model

def get_subgraph (g):
    sub = []
    root = g.get_root_subgraph()
    sub = [ s for s in root.toposort_child_subgraph()
            if s.has_attr("device") and s.get_attr("device").upper() == "DPU"]
    return sub

def get_child_subgraph_dpu(graph: "Graph") -> List["Subgraph"]:
    assert graph is not None, "'graph' should not be None."
    root_subgraph = graph.get_root_subgraph()
    assert (root_subgraph is not None), "Failed to get root subgraph of input Graph object."
    if root_subgraph.is_leaf:
        return []
    child_subgraphs = root_subgraph.toposort_child_subgraph()
    assert child_subgraphs is not None and len(child_subgraphs) > 0
    return [
        cs
        for cs in child_subgraphs
        if cs.has_attr("device") and cs.get_attr("device").upper() == "DPU"
    ]



"""
Calculate softmax
data: data to be calculated
size: data size
return: softamx result
"""
import math
def CPUCalcSoftmax(data, size):
    sum = 0.0
    result = [0 for i in range(size)]
    for i in range(size):
        result[i] = math.exp(data[i])
        sum += result[i]
    for i in range(size):
        result[i] /= sum
    return result

"""
Get topk results according to its probability
datain: data result of softmax
filePath: filePath in witch that records the infotmation of kinds
"""

def TopK(datain, size, filePath):

    cnt = [i for i in range(size)]
    pair = zip(datain, cnt)
    pair = sorted(pair, reverse=True)
    softmax_new, cnt_new = zip(*pair)
    fp = open(filePath, "r")
    data1 = fp.readlines()
    fp.close()
    for i in range(5):
        idx = 0
        for line in data1:
            if idx == cnt_new[i]:
                print("Top[%d] %d %s" % (i, idx, (line.strip)("\n")))
            idx = idx + 1

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()  
ap.add_argument('-m', '--model',     type=str, default='asl_classifier.xmodel', help='Path of xmodel. Default is asl_classifier.xmodel')

args = ap.parse_args()  
  
print ('Command line options:')
print (' --model     : ', args.model)

#dpu_arch = detect_dpu_architecture()
#print('[INFO] Detected DPU architecture : ',dpu_arch)
#
#model_path = './model_1/'+dpu_arch+'/asl_classifier_1.xmodel'
#print('[INFO] ASL model : ',model_path)
model_path = args.model


# Create DPU runner
g = xir.Graph.deserialize(model_path)
subgraphs = get_child_subgraph_dpu(g)
assert len(subgraphs) == 1 # only one DPU kernel
dpu = vart.Runner.create_runner(subgraphs[0], "run")
# input scaling
input_fixpos = dpu.get_input_tensors()[0].get_attr("fix_point")
input_scale = 2**input_fixpos
print('[INFO] input_fixpos=',input_fixpos,' input_scale=',input_scale)

# Get input/output tensors
inputTensors = dpu.get_input_tensors()
outputTensors = dpu.get_output_tensors()
inputShape = inputTensors[0].dims
outputShape = outputTensors[0].dims

print("================================")
print("ASL Classification Demo:")
print("\tPress ESC to quit ...")
print("\tPress 'p' to pause video ...")
print("\tPress 'c' to continue ...")
print("\tPress 's' to step one frame at a time ...")
print("\tPress 'w' to take a photo ...")
print("================================")

step = False
pause = False

image = []
output = []

frame_count = 0

# init the real-time FPS counter
rt_fps_count = 0
rt_fps_time = cv2.getTickCount()
rt_fps_valid = False
rt_fps = 0.0
rt_fps_message = "FPS: {0:.2f}".format(rt_fps)
rt_fps_x = int(10*scale)
rt_fps_y = int((frame_height-10)*scale)

id_to_class = {
  0 :"A",
  1 :"B",
  2 :"C",
  3 :"D",
  4 :"E",
  5 :"F",
  6 :"G",
  7 :"H",
  8 :"I",
  9 :"J",
  10:"K",
  11:"L",
  12:"M",
  13:"N",
  14:"O",
  15:"P",
  16:"Q",
  17:"R",
  18:"S",
  19:"T",
  20:"U",
  21:"V",
  22:"W",
  23:"X",
  24:"Y",
  25:"Z",
  26:"{del}",
  27:"{nothing}",
  28:"{space}"
  }
    
while True:
    # init the real-time FPS counter
    if rt_fps_count == 0:
        rt_fps_time = cv2.getTickCount()

    #if cap.grab():
    if True:
        frame_count = frame_count + 1
        #flag, image = cap.retrieve()
        flag, image = cap.read()
        if not flag:
            break
        else:
            #image = cv2.resize(image,(0,0), fx=scale, fy=scale) 
            output = image.copy()
            
            asl_id = -1
            try:
                # 448x448 ROI for classification
                #y1 = (16)
                #y2 = (16+448)
                #x1 = (96)
                #x2 = (96+448)
                #roi_img = output[ y1:y2, x1:x2, : ]
                #roi_img = cv2.resize(asl_img,(224,224),interpolation=cv2.INTER_CUBIC)
            
                # 224x224 ROI for classification
                y1 = (128)
                y2 = (128+224)
                x1 = (208)
                x2 = (208+224)
                roi_img = output[ y1:y2, x1:x2, : ]
                
                cv2.rectangle(output, (x1,y1), (x2,y2), (0, 255, 0), 2)

                # ASL pre-processing
                asl_img = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
                asl_img = asl_img*input_scale
                asl_img = asl_img.astype(np.int8)
                #cv2.imshow('asl_img',asl_img)
                asl_x = []
                asl_x.append( asl_img )
                asl_x = np.array(asl_x)

                # ASL model execution
                #asl_y = model.predict(asl_x)

                """ Prepare input/output buffers """
                #print("[INFO] ASL - prep input buffer ")
                inputData = []
                inputData.append(np.empty((inputShape),dtype=np.int8,order='C'))
                inputImage = inputData[0]
                inputImage[0,...] = asl_img

                #print("[INFO] ASL - prep output buffer ")
                outputData = []
                outputData.append(np.empty((outputShape),dtype=np.int8,order='C'))

                """ Execute model on DPU """
                #print("[INFO] ASL - execute ")
                job_id = dpu.execute_async( inputData, outputData )
                dpu.wait(job_id)

                # ASL post-processing
                #print("[INFO] ASL - post-processing ")
                #print(outputData[0].shape)
                OutputData = outputData[0].reshape(1,29)
                asl_y = np.reshape( OutputData, (-1,29) )
                asl_id  = np.argmax(asl_y[0])
                asl_sign = id_to_class[asl_id]

                #print("[INFO] ASL - done ")
                asl_text = '['+str(asl_id)+']='+asl_sign
                cv2.putText(output,asl_text,(10,30),text_fontType,text_fontSize,text_color,text_lineSize,text_lineType)
                        
            except:
                print("ERROR : Exception occured during ASL classification ...")

                         
            matching_text = ("[%04d] [%02d]=%s"%(frame_count,asl_id,asl_sign))
            print(matching_text)
                
            # display real-time FPS counter (if valid)
            if rt_fps_valid == True:
                cv2.putText(output,rt_fps_message, (rt_fps_x,rt_fps_y),text_fontType,text_fontSize,text_color,text_lineSize,text_lineType)
            
            # show the output image
            cv2.imshow("ASL Classification", output)

    if step == True:
        key = cv2.waitKey(0)
    elif pause == True:
        key = cv2.waitKey(0)
    else:
        key = cv2.waitKey(10)

    #print(key)
    
    if key == 119: # 'w'
        filename = ("frame%04d_asl%02d.tif"%(frame_count,asl_id))
            
        print("Capturing ",filename," ...")
        cv2.imwrite(os.path.join(output_dir,filename),roi_img)
       
    if key == 115: # 's'
        step = True    
    
    if key == 112: # 'p'
        pause = not pause

    if key == 99: # 'c'
        step = False
        pause = False

    if key == 27 or key == 113: # ESC or 'q':
        break

    # Update the real-time FPS counter
    rt_fps_count = rt_fps_count + 1
    if rt_fps_count == 10:
        t = (cv2.getTickCount() - rt_fps_time)/cv2.getTickFrequency()
        rt_fps_valid = 1
        rt_fps = 10.0/t
        rt_fps_message = "FPS: {0:.2f}".format(rt_fps)
        #print("[INFO] ",rt_fps_message)
        rt_fps_count = 0



# Stop the ASL classifier
del dpu

# Cleanup
cv2.destroyAllWindows()
