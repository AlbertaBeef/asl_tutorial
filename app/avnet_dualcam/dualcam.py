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

# Based on DualCam 2022.2 Designs
#    http://avnet.me/u96v2-dualcam-2022.2
#    http://avnet.me/zub1cg-dualcam-2022.2
    
import numpy as np
import cv2
import os
import glob
import subprocess
import re

def get_media_dev_by_name(src):
    devices = glob.glob("/dev/media*")
    for dev in devices:
        proc = subprocess.run(['media-ctl','-d',dev,'-p'], capture_output=True, encoding='utf8')
        for line in proc.stdout.splitlines():
            if src in line:
                return dev

def get_video_dev_by_name(src):
    devices = glob.glob("/dev/video*")
    for dev in devices:
        proc = subprocess.run(['v4l2-ctl','-d',dev,'-D'], capture_output=True, encoding='utf8')
        for line in proc.stdout.splitlines():
            if src in line:
                return dev

def get_ap1302_i2c_desc(dev_media):
    proc = subprocess.run(['media-ctl','-d',dev_media,'-p'], capture_output=True, encoding='utf8')
    for line in proc.stdout.splitlines():
        if 'ap1302' in line:
            #     <- "ap1302.0-003c":2 [ENABLED]
            i2c_bus = re.search('ap1302.(.+?)-003c', line).group(1)
            ap1302_i2c_desc = 'ap1302.'+i2c_bus+'-003c'            
            return ap1302_i2c_desc

def get_mipi_desc(dev_media):
    proc = subprocess.run(['media-ctl','-d',dev_media,'-p'], capture_output=True, encoding='utf8')
    for line in proc.stdout.splitlines():
        if not 'entity' in line:
            if 'mipi_csi2_rx_subsystem' in line:
                #                 <- "b0000000.mipi_csi2_rx_subsystem":1 [ENABLED]
                #                 -> "b0000000.mipi_csi2_rx_subsystem":0 [ENABLED]
                base_address = re.search('\"(.+?).mipi_csi2_rx_subsystem', line).group(1)
                mipi_desc = base_address+'.mipi_csi2_rx_subsystem'
                return mipi_desc
          
def get_csc_desc(dev_media):
    proc = subprocess.run(['media-ctl','-d',dev_media,'-p'], capture_output=True, encoding='utf8')
    for line in proc.stdout.splitlines():
        if not 'entity' in line:
            if 'v_proc_ss' in line:
                #                 <- "b0040000.v_proc_ss":1 [ENABLED]
                #                 <- "b0020000.v_proc_ss":1 [ENABLED]
                #                 -> "b0020000.v_proc_ss":0 [ENABLED]
                #                 -> "b0040000.v_proc_ss":0 [ENABLED]
                base_address = re.search('"(.+?).v_proc_ss', line).group(1)
                driver_desc = 'v_proc_ss@'+base_address
                proc2 = subprocess.run(['find','/sys/firmware/devicetree','-name',driver_desc],capture_output=True, encoding='utf8')
                driver_path = proc2.stdout.splitlines()[0]
                proc3 = subprocess.run(['cat',driver_path+'/compatible'],capture_output=True, encoding='utf8')
                driver_compatible = proc3.stdout.splitlines()[0]
                if 'xlnx,v-vpss-csc' in driver_compatible:
                    csc_desc = base_address+'.v_proc_ss'            
                    return csc_desc

def get_scaler_desc(dev_media):
    proc = subprocess.run(['media-ctl','-d',dev_media,'-p'], capture_output=True, encoding='utf8')
    for line in proc.stdout.splitlines():
        if not 'entity' in line:
            if 'v_proc_ss' in line:
                #                 <- "b0040000.v_proc_ss":1 [ENABLED]
                #                 <- "b0020000.v_proc_ss":1 [ENABLED]
                #                 -> "b0020000.v_proc_ss":0 [ENABLED]
                #                 -> "b0040000.v_proc_ss":0 [ENABLED]
                base_address = re.search('"(.+?).v_proc_ss', line).group(1)
                driver_desc = 'v_proc_ss@'+base_address
                proc2 = subprocess.run(['find','/sys/firmware/devicetree','-name',driver_desc],capture_output=True, encoding='utf8')
                driver_path = proc2.stdout.splitlines()[0]
                proc3 = subprocess.run(['cat',driver_path+'/compatible'],capture_output=True, encoding='utf8')
                driver_compatible = proc3.stdout.splitlines()[0]
                if 'xlnx,v-vpss-scaler' in driver_compatible:
                    scaler_desc = base_address+'.v_proc_ss'            
                    return scaler_desc                      
                        
def get_platform_name():
    proc = subprocess.run(['hostname'], capture_output=True, encoding='utf8')
    for line in proc.stdout.splitlines():
        platform_name = re.search('(.+?)-sbc-(.+?)',line).group(1)
        return platform_name

class DualCam():
	  
  def __init__(self, cap_sensor='ar0144', cap_mode='dual', cap_width=1280, cap_height=800):
  
    #self.cap_config = cap_config
    self.cap_sensor = cap_sensor
    self.cap_mode = cap_mode
    self.cap_width = cap_width
    self.cap_height = cap_height

    self.platform_name = get_platform_name()
    print("\n\r[DualCam] hostname = ",self.platform_name) 
    
    self.input_resolution = 'WxH'
    self.output_width = 0
    self.output_height = 0
    self.output_resolution = 'WxH'

    if cap_sensor == 'ar0144' and (cap_mode == 'dual'):
      self.input_resolution = '2560x800' # 2 x 1280x800
      self.output_width = self.cap_width*2
      self.output_height = self.cap_height
      self.output_resolution = str(self.output_width)+'x'+str(self.output_height)
    elif cap_sensor == 'ar0144' and (cap_mode == 'primary' or cap_mode == 'secondary'):
      self.input_resolution = '1280x800'
      self.output_width = self.cap_width
      self.output_height = self.cap_height
      self.output_resolution = str(self.output_width)+'x'+str(self.output_height)
    elif cap_sensor == 'ar1335' and (cap_mode == 'primary' or cap_mode == 'secondary'):
      if self.platform_name == 'zub1cg':
        self.input_resolution = '1920x1080'
      else:
        self.input_resolution = '3840x2160'
      self.output_width = self.cap_width
      self.output_height = self.cap_height
      self.output_resolution = str(self.output_width)+'x'+str(self.output_height)
    elif cap_sensor == 'ar1335' and (cap_mode == 'dual'):
      self.input_resolution = '3840x1080' # 2 x 1920x1080
      self.output_width = self.cap_width*2
      self.output_height = self.cap_height
      self.output_resolution = str(self.output_width)+'x'+str(self.output_height)
    elif cap_sensor == 'ar0830' and (cap_mode == 'primary' or cap_mode == 'secondary'):
      if self.platform_name == 'zub1cg':
        self.input_resolution = '1920x1080'
      else:
        self.input_resolution = '3840x2160'
      self.output_width = self.cap_width
      self.output_height = self.cap_height
      self.output_resolution = str(self.output_width)+'x'+str(self.output_height)
    elif cap_sensor == 'ar0830' and (cap_mode == 'dual'):
      self.input_resolution = '3840x1080' # 2 x 1920x1080
      self.output_width = self.cap_width*2
      self.output_height = self.cap_height
      self.output_resolution = str(self.output_width)+'x'+str(self.output_height)
    else:
      print("[DualCam] Invalid cap_sensor|cap_mode = ",cap_sensor,cap_mode," !  (must be {ar0144|ar1335|ar0830}|{primary|secondary|dual})")
      return None

    print("\n\r[DualCam] Looking for devices corresponding to AP1302")
    dev_video = get_video_dev_by_name("vcap_CAPTURE_PIPELINE_v_proc_ss")
    dev_media = get_media_dev_by_name("vcap_CAPTURE_PIPELINE_v_proc_ss")
    #ap1302_i2c_desc = get_ap1302_i2c_desc(dev_media)
    print('\tdev_video = ',dev_video)
    print('\tdev_media = ',dev_media)
    #print(ap1302_i2c_desc)
    self.dev_video = dev_video
    self.dev_media = dev_media
    #self.ap1302_i2c_desc = ap1302_i2c_desc

    proc1 = subprocess.run(['find','/sys/firmware/devicetree','-name','sensor,model'],capture_output=True, encoding='utf8')
    sensor_path = proc1.stdout.splitlines()[0]
    proc2 = subprocess.run(['cat',sensor_path],capture_output=True, encoding='utf8')
    sensor_type = proc2.stdout.splitlines()[0]
    # hack to get rid of embedded null byte
    if 'ar0144' in sensor_type:
        sensor_type = 'ar0144'
    if 'ar1335' in sensor_type:
        sensor_type = 'ar1335'
    if 'ar0830' in sensor_type:
        sensor_type = 'ar0830'
    proc3 = subprocess.run(['ls','/sys/bus/i2c/drivers/ap1302'],capture_output=True, encoding='utf8')
    ap1302_i2c = proc3.stdout.splitlines()[0]
    ap1302_dev = "ap1302."+ap1302_i2c
    ap1302_sensor = ap1302_i2c+"."+sensor_type
    #print('\tsensor_path = ',sensor_path)
    print('\tsensor_type = ',sensor_type)
    print('\tap1302_i2c = ',ap1302_i2c)
    print('\tap1302_dev = ',ap1302_dev)
    print('\tap1302_sensor = ',ap1302_sensor)
    self.ap1302_i2c = ap1302_i2c
    self.ap1302_dev = ap1302_dev
    self.ap1302_sensor = ap1302_sensor

    print("\n\r[DualCam] Looking for base address for MIPI capture pipeline")
    mipi_desc = get_mipi_desc(dev_media)
    csc_desc = get_csc_desc(dev_media)
    scaler_desc = get_scaler_desc(dev_media)
    print('\tmipi_desc = ',mipi_desc)
    print('\tcsc_desc = ',csc_desc)
    print('\tscaler_desc = ',scaler_desc)
    self.mipi_desc = mipi_desc
    self.csc_desc = csc_desc
    self.scaler_desc = scaler_desc
            
    if self.platform_name == 'zub1cg':
      # HSIO dualcam : sensors placed left-right on board
      print("\n\r[DualCam] Detected HSIO dualcam (sensors placed left-right on board)")
    else:
      # 96Boards dualcam : sensors places right-left on board
      print("\n\r[DualCam] Detected 96Boards dualcam (sensors placed right-left on board)")
      
    if self.cap_mode == 'primary':
        print("\n\r[DualCam] Initializing AP1302 for primary sensor")
        cmd = "media-ctl -d "+dev_media+" -l '\""+ap1302_sensor+".0\":0 -> \""+ap1302_dev+"\":0[1]'"
        print(cmd)
        os.system(cmd)
        cmd = "media-ctl -d "+dev_media+" -l '\""+ap1302_sensor+".1\":0 -> \""+ap1302_dev+"\":1[0]'"
        print(cmd)
        os.system(cmd)
    elif self.cap_mode == 'secondary':
        print("\n\r[DualCam] Initializing AP1302 for secondary sensor")
        cmd = "media-ctl -d "+dev_media+" -l '\""+ap1302_sensor+".0\":0 -> \""+ap1302_dev+"\":0[0]'"
        print(cmd)
        os.system(cmd)
        cmd = "media-ctl -d "+dev_media+" -l '\""+ap1302_sensor+".1\":0 -> \""+ap1302_dev+"\":1[1]'"
        print(cmd)
        os.system(cmd)
    elif self.cap_mode == 'dual':
        print("\n\r[DualCam] Initializing AP1302 for dual sensors")
        cmd = "media-ctl -d "+dev_media+" -l '\""+ap1302_sensor+".0\":0 -> \""+ap1302_dev+"\":0[1]'"
        print(cmd)
        os.system(cmd)
        cmd = "media-ctl -d "+dev_media+" -l '\""+ap1302_sensor+".1\":0 -> \""+ap1302_dev+"\":1[1]'"
        print(cmd)
        os.system(cmd)
    else:
        print("\n\r[DualCam] Unsupported mode ",self.cap_mode)

    print("\n\r[DualCam] Initializing capture pipeline for ",self.cap_sensor,self.cap_mode,self.cap_width,self.cap_height)
            
    cmd = "media-ctl -d "+dev_media+" -V \"'"+ap1302_dev+"':2 [fmt:UYVY8_1X16/"+self.input_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)

    cmd = "media-ctl -d "+dev_media+" -V \"'"+mipi_desc+"':0 [fmt:UYVY8_1X16/"+self.input_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)
    cmd = "media-ctl -d "+dev_media+" -V \"'"+mipi_desc+"':1 [fmt:UYVY8_1X16/"+self.input_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)

    cmd = "media-ctl -d "+dev_media+" -V \"'"+csc_desc+"':0 [fmt:UYVY8_1X16/"+self.input_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)
    cmd = "media-ctl -d "+dev_media+" -V \"'"+csc_desc+"':1 [fmt:RBG24/"+self.input_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)

    cmd = "media-ctl -d "+dev_media+" -V \"'"+scaler_desc+"':0 [fmt:RBG24/"+self.input_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)
    cmd = "media-ctl -d "+dev_media+" -V \"'"+scaler_desc+"':1 [fmt:RBG24/"+self.output_resolution+" field:none]\""
    print(cmd)
    os.system(cmd)

    #cmd = "v4l2-ctl -d "+dev_video+"  --set-fmt-video=width="+str(self.output_width)+",height="+str(self.output_height)+",pixelformat=BGR3"
    #print(cmd)
    #os.system(cmd)

    if cap_sensor == 'ar0144':
       print("\n\r[DualCam] Disabling Auto White Balance")
       cmd = "v4l2-ctl --set-ctrl white_balance_auto_preset=0 -d "+dev_video
       print(cmd)
       os.system(cmd)

    #if cap_sensor == 'ar0144' and cap_mode == 'dual':
    #  print("\n\r[DualCam] Configuring AP1302 for left-right side-by-side configuration")
    #  cmd = "v4l2-ctl --set-ctrl 3d_path=1 -d "+dev_video
    #  print(cmd)
    #  os.system(cmd)
    # causes capture to hange ... cannot use :(

    if cap_sensor == 'ar1335':
      print("\n\r[DualCam] Configuring AP1302 for no horizontal/vertical flip")

      cmd = "v4l2-ctl --set-ctrl vflip=0 -d "+dev_video
      print(cmd)
      os.system(cmd)

      cmd = "v4l2-ctl --set-ctrl hflip=0 -d "+dev_video
      print(cmd)
      os.system(cmd)

      print("\n\r[DualCam] Configuring AP1302 to enable auto-focus")

      cmd = "v4l2-ctl --set-ctrl auto_focus=1 -d "+dev_video
      print(cmd)
      os.system(cmd)

    print("\n\r[DualCam] Opening cv2.VideoCapture for ",self.output_width,self.output_height)

    gst_pipeline = "v4l2src device="+dev_video+" io-mode=\"dmabuf\" ! video/x-raw, width="+str(self.output_width)+", height="+str(self.output_height)+", format=BGR, framerate=60/1 ! appsink" 
    print("GStreamer pipeline = "+gst_pipeline)
    self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,self.output_width)
    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,self.output_height)

    print("\n\r")

  def set_brightness(self,brightness):
    print("\n\r[DualCam] Setting brightness to ",brightness)
    cmd = "v4l2-ctl --set-ctrl brightness="+str(brightness)+" -d "+self.dev_video
    print(cmd)
    os.system(cmd)
    
  def set_exposure(self,exposure):
    print("\n\r[DualCam] Setting exposure to ",exposure)
    cmd = "v4l2-ctl --set-ctrl exposure="+str(exposure)+" -d "+self.dev_video
    print(cmd)
    os.system(cmd)
    
    
  def capture(self):
    
    if not (self.cap.grab()):
      print("[DualCam] No more frames !")
      return None

    _, frame = self.cap.retrieve()
    
    return frame
  

  def capture_dual(self):
    
    if not (self.cap.grab()):
      print("[DualCam] No more frames !")
      return None

    _, frame = self.cap.retrieve()
    
    if self.platform_name == 'zub1cg':
      # HSIO dualcam : sensors placed left-right on board
      left  = frame[:,1:(self.cap_width)+1,:]
      right = frame[:,(self.cap_width):(self.cap_width*2)+1,:]
    else:
      # 96Boards dualcam : sensors places right-left on board
      right = frame[:,1:(self.cap_width)+1,:]
      left  = frame[:,(self.cap_width):(self.cap_width*2)+1,:]    
    
    return left,right    
  

  def release(self):
  
    self.cap_dual = True
    self.cap_width = 0
    self.cap_height = 0

    self.input_resolution = 'WxH'
    self.output_width = 0
    self.output_height = 0
    self.output_resolution = 'WxH'

    self.dev_video = ""
    self.dev_media = ""
    
    del self.cap
    self.cap = None


