from djitellopy import tello
import keyPressModule as kp
import time
import cv2
import handTrackingModule as htm
import handGestureModule as hgm
import queueModule as qm
import trackingModule as tm
import normalizePointsModule as normalize
from numba import jit
import numpy as np
import pdb
import os

import matplotlib.pyplot as plt

from screeninfo import get_monitors


class FullControll():

    def __init__(self, 
                getFromWebcam: bool, 
                nameWindowWebcam: str, 
                resize: bool, 
                xResize: int, 
                yResize: int, 
                detector: htm.handDetector,
                gestureDetector: hgm.handGestureRecognition,
                normalizedPoints: normalize.normalizePoints,
                tracking: tm.tracking):

        self.getFromWebcam = getFromWebcam
        self.nameWindowWebcam = nameWindowWebcam
        self.resize = resize
        self.xResize = xResize
        self.yResize = yResize
        self.detector = detector
        self.gestureDetector = gestureDetector
        self.normalizedPoints = normalizedPoints
        self.tracking = tracking
       

    def getKeyboardInput(self, me: tello.Tello, img: np.array) -> list:
        """
        Get keyboard input to move the drone a fixed speed using a controller.
        Speed can be increased or decresed dinamically.

        Arguments:
            me: this permits to takeoff or land the drone
            img: save this img if getKey('z')
        """

        #left-right, foward-back, up-down, yaw velocity
        lr, fb, ud, yv = 0, 0, 0, 0
        speed = 30

        if kp.getKey("LEFT"): lr = -speed
        elif kp.getKey("RIGHT"): lr = speed

        if kp.getKey("UP"): fb = speed
        elif kp.getKey("DOWN"): fb = -speed

        if kp.getKey("w"): ud = speed
        elif kp.getKey("s"): ud = -speed

        if kp.getKey("a"): yv = speed
        elif kp.getKey("d"): yv = -speed

        if kp.getKey("e"): me.takeoff(); time.sleep(3) # this allows the drone to takeoff
        if kp.getKey("q"): me.land() # this allows the drone to land

        if kp.getKey('z'):
            cv2.imwrite(f'src/tello_screenshots/{time.time()}.jpg', img)
            time.sleep(0.3)

        return [lr, fb, ud, yv]


    def isWebcamOrDrone(self):
        """
        This function set parameters to work with webcam or drone camera
        """

        # HERE MAYBE COULD BE USEFUL USE A FACTORY FUNCTION (FROM SOFTWARE ENGENEERING)
        if self.getFromWebcam:
            
            # OPEN WEBCAM
            cv2.namedWindow(self.nameWindowWebcam)

            cv2.moveWindow(self.nameWindowWebcam, 0, int( get_monitors()[0].height / 2 ) + 10)

            # For Linux, make sure OpenCV is built using the WITH_V4L (with video for linux).
            # sudo apt install v4l-utils
            # https://www.youtube.com/watch?v=ec4-1gF-cNU
            if os.name == 'posix': # if linux system
                cap = cv2.VideoCapture(0)
            elif os.name == 'nt': # if windows system
                cap = cv2.VideoCapture(0,cv2.CAP_DSHOW)

            #Check if camera was opened correctly
            if cap.isOpened():

                # try to get the first frame
                success, img = cap.read()

                # set size
                if self.resize:
                    self.tracking.setSize(self.xResize, self.yResize)
                    self.normalizedPoints.setSize(self.xResize, self.yResize)
                else:
                    height, width, _ = img.shape
                    self.tracking.setSize(height, width)
                    self.normalizedPoints.setSize(height, width)
            else:
                success = False

            return img, cap, None

        else:
            kp.init()
            me = tello.Tello()
            me.connect()
            me.streamon() # to get the stream image

            # set size
            img = me.get_frame_read().frame
            if self.resize:
                self.tracking.setSize(self.xResize, self.yResize)
            else:
                height, width, _ = img.shape
                self.tracking.setSize(height, width)

            return img, None, me
            

    def run(self):
        """
        Execute the algorithm to detect the 3D trajectories from 2D hand landmarks
        """

        # define variable to compute framerate
        pTime = 0
        cTime = 0

        img, cap, me = self.isWebcamOrDrone()

        while True:

            if self.getFromWebcam:
                success, img = cap.read()
                img = cv2.flip(img, 1)

            else:
                vals = self.getKeyboardInput(me, img)
                if not (vals[0] == vals[1] == vals[2] == vals[3] == 0):
                    me.send_rc_control(vals[0], vals[1], vals[2], vals[3])
                    time.sleep(0.05)

                img = me.get_frame_read().frame
                img = cv2.flip(img, 1)

                # print drone battery on screen
                fontScale = 1
                font = cv2.FONT_HERSHEY_DUPLEX
                thickness = 1
                color = (0,0,255)
                img = cv2.putText(img, 
                                    f"Battery: {me.get_battery()}", 
                                    (10, self.tracking.height-5),
                                    font, 
                                    fontScale, 
                                    color, 
                                    thickness)

            if self.resize:
                img = cv2.resize(img, (self.xResize, self.yResize)) # comment to get bigger frames
                img = cv2.flip(img, 1)
            
            img = self.detector.findHands(img)
            lmList = self.detector.findPosition(img, draw=False)

            if len(lmList) != 0:
                # setArray, computeMean, normalize points, and draw
                self.normalizedPoints.setArray(lmList)
                self.normalizedPoints.normalize()
                self.normalizedPoints.drawAllHandTransformed(img)
                self.normalizedPoints.removeHomogeneousCoordinate()

                # hand gesture recognition
                img, outputClass, probability = self.gestureDetector.processHands(img, self.normalizedPoints)
                res = self.tracking.run(img, self.normalizedPoints, outputClass, probability)
                
                if res is not None:
                    return res
            else:
                self.tracking.justDrawLast2dTraj(img)


            cTime = time.time()
            fps = 1/(cTime-pTime)
            pTime = cTime

            fontScale = 1
            font = cv2.FONT_HERSHEY_DUPLEX
            thickness = 1
            cv2.putText(img, f"FPS: {int(fps)}", (10,40), font, fontScale, (255,0,255), thickness) # print fps

            cv2.imshow(self.nameWindowWebcam, img)
            key = cv2.waitKey(1)
            if key == 27: # exit on ESC
                break


def main():

    global img

    # Set if webcam or drone camera source
    # True is webcam, False is drone camera
    getFromWebcam = True

    # Set name window of imshow
    nameWindowWebcam = "Image"

    # Set if resize input img
    # if resize is True then width = xResize and height = yResize
    resize = False
    xResize = 360
    yResize = 240

    # Istantiate handDetector obj
    detector = htm.handDetector()

    #Istantiate handGestureRecognition obj
    gestureDetector = hgm.handGestureRecognition()

    # Istantiate normalizePoints obj
    normalizedPoints = normalize.normalizePoints()

    # Create a queue obj of a certain length 
    queue = qm.queueObj(lenMaxQueue=35)

    # Instantite tracking obj
    showPlot = True
    tracking = tm.tracking(queue, 
                            skipEveryNpoints=4, 
                            trajTimeDuration=10, # trajTimeDuration is in seconds
                            log3D=showPlot) 

    # Instantite FullControll obj
    fullControll = FullControll(getFromWebcam, 
                                nameWindowWebcam, 
                                resize, 
                                xResize, 
                                yResize, 
                                detector,
                                gestureDetector,
                                normalizedPoints,
                                tracking)
    fullControll.run()


if __name__ == "__main__":
    
    main()