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

    def getKeyboardInput(self, me: tello.Tello, img: np.array) -> list:
        """
        Get keyboard input to move the drone a fixed speed using a controller.
        Speed can be increased or decresed dinamically.
        Arguments:
            me: this permits to takeoff or land the drone
            img: save this img if getKey('z')
        """

        # left-right, foward-back, up-down, yaw velocity
        lr, fb, ud, yv = 0, 0, 0, 0
        speed = 30

        if kp.getKey("LEFT"):
            lr = -speed
        elif kp.getKey("RIGHT"):
            lr = speed

        if kp.getKey("UP"):
            fb = speed
        elif kp.getKey("DOWN"):
            fb = -speed

        if kp.getKey("w"):
            ud = speed
        elif kp.getKey("s"):
            ud = -speed

        if kp.getKey("a"):
            yv = speed
        elif kp.getKey("d"):
            yv = -speed

        if kp.getKey("e"): me.takeoff(); time.sleep(3)  # this allows the drone to takeoff
        if kp.getKey("q"): me.land()  # this allows the drone to land

        if kp.getKey('z'):
            cv2.imwrite(f'src/tello_screenshots/{time.time()}.jpg', img)
            time.sleep(0.3)

        return [lr, fb, ud, yv]

    def isWebcamOrDrone(self, me):
        """
        This function set parameters to work with webcam or drone camera
        """

        # HERE MAYBE COULD BE USEFUL USE A FACTORY FUNCTION (FROM SOFTWARE ENGENEERING)
        if self.getFromWebcam:

            # OPEN WEBCAM
            cv2.namedWindow(self.nameWindowWebcam)

            cv2.moveWindow(self.nameWindowWebcam, 0, int(get_monitors()[0].height / 2) + 10)

            # For Linux, make sure OpenCV is built using the WITH_V4L (with video for linux).
            # sudo apt install v4l-utils
            # https://www.youtube.com/watch?v=ec4-1gF-cNU
            if os.name == 'posix':  # if linux system
                cap = cv2.VideoCapture(0)
            elif os.name == 'nt':  # if windows system
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

            # Check if camera was opened correctly
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

            return img, cap

        else:
            # set size
            img = me.get_frame_read().frame
            if self.resize:
                self.tracking.setSize(self.xResize, self.yResize)
            else:
                height, width, _ = img.shape
                self.tracking.setSize(height, width)

            return img, None

    def closekp(self):

        kp.close()

    def run(self, me=None):
        """
        Execute the algorithm to detect the 3D trajectories from 2D hand landmarks
        """

        if not self.isSimulation:
            kp.init()

        # Define variable to compute framerate
        pTime = 0
        cTime = 0

        img, cap = self.isWebcamOrDrone(me)

        # Save video from camera
        if self.getFromWebcam:
            height, width = self.getResolution()
            video = cv2.VideoWriter(f'{self.path}_webcam.avi', cv2.VideoWriter_fourcc(*'XVID'), 30, (width, height))

        while True:

            if self.getFromWebcam:
                success, img = cap.read()
                img = cv2.flip(img, 1)

            else:
                img = me.get_frame_read().frame
                img = cv2.flip(img, 1)

                # print drone battery on screen
                fontScale = 1
                font = cv2.FONT_HERSHEY_DUPLEX
                thickness = 1
                color = (0, 0, 255)
                img = cv2.putText(img,
                                  f"Battery: {me.get_battery()}",
                                  (10, self.tracking.height - 5),
                                  font,
                                  fontScale,
                                  color,
                                  thickness)

            if self.resize:
                img = cv2.resize(img, (self.xResize, self.yResize))  # comment to get bigger frames

            # Control with joystick
            if not self.isSimulation:
                # If we get some action from joystick then send rc, else no set anything
                # because the command me.send_rc_control(0, 0, 0, 0) will be send
                # in self.tracking.run() function always
                # need to refactor this getKeyboardInput-> so if the keyboard is not pressed then return None and not [0,0,0,0]
                vals = self.getKeyboardInput(me, img)
                if not (vals[0] == vals[1] == vals[2] == vals[3] == 0):
                    me.send_rc_control(vals[0], vals[1], vals[2], vals[3])
                    # print(f"vals are :{vals[0]}, {vals[1]}, {vals[2]}, {vals[3]}")

            img = self.detector.findHands(img, drawHand="LEFT")
            lmList = self.detector.findPosition(img, draw=False)

            if len(lmList) != 0:
                # setArray, computeMean, normalize points, and draw
                self.normalizedPoints.setArray(lmList)
                self.normalizedPoints.normalize()
                self.normalizedPoints.removeHomogeneousCoordinate()
                # all of these "" self.normalizedPoints.setArray(lmList)
                #                 self.normalizedPoints.normalize()
                #                 self.normalizedPoints.removeHomogeneousCoordinate()""
                # are preprocessing function of a gesture recognition model

                # Hand gesture recognition
                # we detect after normalization: translate origin, scale wrt max distance
                img, outputClass, probability = self.gestureDetector.processHands(img, self.normalizedPoints)

                # Scale a little bit
                # we need to avoid this addHomogeneousCoordinate and remove by delegating responsibilities to different classes
                self.normalizedPoints.addHomogeneousCoordinate()
                self.normalizedPoints.scaleLittle()  #Currently essential for computing orientation
                if self.allHandTransformed:
                    # consider drawing hands before scaling the hand landmarks, this simplifies the code
                    self.normalizedPoints.drawAllHandTransformed(img)

                # Rotate Points, needed to compute yaw and pitch
                self.normalizedPoints.rotatePoints()
                self.normalizedPoints.removeHomogeneousCoordinate()

                # Compute Mean point and draw it
                val = self.normalizedPoints.mean.astype(int)
                #draw point p
                cv2.circle(img, (val[0], val[1]), radius=3, color=(0, 255, 0), thickness=3)

                # Compute Orientation
                roll, yaw, pitch = self.normalizedPoints.computeOrientation()

                # Draw DrawFixedHand
                self.normalizedPoints.drawFixedHand(img, roll, yaw, pitch)

                self.normalizedPoints.computeDepth(roll, yaw, pitch)
                self.normalizedPoints.drawOrientationVector(img, roll, yaw, pitch)

                # Execute commands
                res = self.tracking.run(img, self.normalizedPoints, outputClass, probability, me, val, roll, yaw, pitch,
                                        self.isSimulation)

                if res is not None:
                    # Close video and return data
                    if self.getFromWebcam:
                        video.release()

                    return res
            else:
                self.tracking.justDrawLast2dTraj(img)

            # Update framerate
            cTime = time.time()
            fps = 1 / (cTime - pTime)
            pTime = cTime

            fontScale = 1
            font = cv2.FONT_HERSHEY_DUPLEX
            thickness = 1
            cv2.putText(img, f"FPS: {int(fps)}", (10, 40), font, fontScale, (255, 0, 255), thickness)  # print fps

            # Write the flipped frame
            if self.getFromWebcam:
                video.write(img)

            # Show frame
            cv2.imshow(self.nameWindowWebcam, img)
            if cv2.waitKey(1) & 0xFF == ord('q'):  # exit on ESC
                break

    def getResolution(self):

        return self.tracking.height, self.tracking.width

    def autoSet(self, path, isWebcam=True, resize=False, showPlot=True, isSimulation=False, allHandTransformed=True,
                save3dPlot=False):

        if isSimulation:
            path = os.path.join(os.getcwd(), 'src', 'video_src')
            # path = "/home/usiusi/catkin_ws/src/DJI-Tello-3D-Hand-Gesture-control/src/video_src"

        # Set if webcam or drone camera source
        # True is webcam, False is drone camera
        self.getFromWebcam = isWebcam

        self.isSimulation = isSimulation
        self.allHandTransformed = allHandTransformed
        self.path = path

        # Set name window of imshow
        self.nameWindowWebcam = "Image"

        # Set if resize input img
        # if resize is True then width = xResize and height = yResize
        self.xResize = 360
        self.yResize = 240
        self.resize = resize

        # Istantiate handDetector obj
        self.detector = htm.handDetector()

        # Istantiate handGestureRecognition obj
        self.gestureDetector = hgm.handGestureRecognition()

        # Istantiate normalizePoints obj
        self.normalizedPoints = normalize.normalizePoints()

        # Create a queue obj of a certain length 
        queue = qm.queueObj(lenMaxQueue=35)

        # Instantite tracking obj
        self.tracking = tm.tracking(queue,
                                    skipEveryNsec=0.25,  # 0
                                    skipEveryNpoints=2,  # 4
                                    trajTimeDuration=20,  # trajTimeDuration is in seconds
                                    log3D=showPlot,
                                    save3dPlot=save3dPlot,
                                    path=path)


def setLastIdx(PATH) -> int:
    """
    Create folder "self.VIDEO_DIR_PATH" if doesn't exist and return 1.
    In general, return as index the number of video added +1.

    If folder with n as name already exists, try to create folder
    with n+1 as name, otherwise iterate.

    Update self.VIDEO_DIR_PATH with folder where to put all files
    """

    if not os.path.exists(PATH):
        folder = os.path.join(PATH, str(1))
        if os.name == 'posix':  # if linux system
            os.system(f"mkdir -p {folder}\\1")
        if os.name == 'nt':  # if windows system
            os.system(f"mkdir {folder}\\1")

        PATH = f"{folder}\\{str(1)}"
        return PATH

    nu = len(next(os.walk(PATH))[1]) + 1
    while True:
        # Count number of folders
        folder = os.path.join(PATH, str(nu))
        if not os.path.exists(folder):
            if os.name == 'posix':  # if linux system
                os.system(f"mkdir -p {folder}")
            if os.name == 'nt':  # if windows system
                os.system(f"mkdir {folder}")

            PATH = f"{folder}\\{nu}"
            return PATH
        else:
            nu += 1


def main():
    PATH = os.path.join('src', 'tmp')

    # Path for save things
    PATH = setLastIdx(PATH)

    isWebcam = True
    me = tello.Tello()

    if not isWebcam:
        me.connect()
        print(me.get_battery())

    fullControll = FullControll()

    # save3dPlot works only if showPlot is True
    fullControll.autoSet(path=PATH, isWebcam=isWebcam, resize=False, allHandTransformed=True, showPlot=True,
                         save3dPlot=True)

    fullControll.run(me)

    if not isWebcam:
        me.streamoff()


if __name__ == "__main__":
    main()
