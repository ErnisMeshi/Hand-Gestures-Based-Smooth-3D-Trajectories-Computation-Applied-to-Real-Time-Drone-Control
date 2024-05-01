from typing import Tuple
import numpy as np
import pointManipulationModule as pm
import cv2
import copy
import pdb


class normalizePoints():

    def __init__(self):

        self.transf = pm.pointManipulation()

        # initialize array
        self.tmp = np.zeros((21,2), dtype=np.float32)

        self.mean = 0
        self.lmList = []

        self.height = 0
        self.width = 0

        self.zcoord = 0

        # This variable is to save the first hand (should be evaluated if detect gesture)
        self.firstHandNotScaled = None
        self.currentHandNotScaled = None


    def addHandNotScaled(self):
        if self.firstHandNotScaled is None:
            self.firstHandNotScaled = copy.deepcopy(self.tmp)
        
        self.currentHandNotScaled = copy.deepcopy(self.tmp)


    def setSize(self, height: int, width: int):
        """
        Set size of the window.
        """

        self.transf.setSize(height, width)
        self.height = height
        self.width = width


    def setArray(self, lmList: list):
        """
        Set lmList and compute mean x and y of all hand leandmark.
        """

        # assign value
        self.lmList = lmList # you should check if more than hand detected...
        tmp = self.tmp
        x_sum = y_sum = 0

        for i in range(len(lmList)):
            #remember is a list lmList=[[id1, cx1, cy1],[id2, cx2, cy2]]
            # create numpy array point
            tmp[i] = np.array(lmList[i][1:], dtype=np.float32)

            x_sum += tmp[i][0]
            y_sum += tmp[i][1]

            # to move the origin from top left to bottom left 
            tmp[i] = self.transf.convertOriginBottomLeft(tmp[i])

        self.tmp = tmp
       # self.tmp is a array of hand landmark with coordinates converted with convertOriginBottomLeft method.
        x_mean = x_sum / 21
        y_mean = y_sum / 21
 
        mean = np.array([x_mean, y_mean], dtype=np.float32)
        self.mean = mean # is point p


    def normalize(self):
        """
        Normalize each point using mean, rotatation (to have the hand that always points up)
        and scale respect max distance.
        """

        mean = copy.deepcopy(self.mean) # LASCIA COSì! DOBBIAMO COPIARE SELF.MEAN
        mean = self.transf.convertOriginBottomLeft(mean)

        # Find angle
        theta = self.transf.findAngle(self.tmp[12], self.tmp[0])
        self.theta = theta

        # Convert in homogeneous coordinates
        self.addHomogeneousCoordinate()

        # Since mean point as anchor translate everything to the origin
        self.tmp = self.transf.translate(self.tmp, -mean[0], -mean[1])

        # Add the current hand that is not scaled
        self.addHandNotScaled()

        # Scale everything respect max distance
        self.tmp = self.transf.scaleMaxDistance(self.tmp)     


    def rotatePoints(self):
        # Compute rotation just for wrist and middle_finger_tip
        self.tmp = self.transf.rotatate(self.tmp, self.theta)
        
        # save this info to compute the z-coordinate
        self.wrist = self.tmp[0]
        self.middle_finger_tip = self.tmp[12]


    def getPointsForNet(self):
        """
        Gives a new shape to an array without changing its data.
        One shape dimension can be -1. In this case, the value is inferred from
        the length of the array and remaining dimensions.
        """

        return self.tmp.reshape(-1)


    def computeOrientation(self) -> Tuple[float, float, float]:
        """
        Compute roll, yaw and pitch.
        """

        roll = self.computeRoll()
        yaw = self.computeYaw(roll)
        pitch = self.computePitch()

        return roll, yaw, pitch


    def computeRoll(self) -> float:
        """
        Compute roll.
        """

        thetadeg = self.theta * 180 / np.pi

        return -thetadeg


    def computeYaw(self, roll: float) -> float:
        """
        Compute Yaw.
        """

        if roll < - 5: # "-90"
            tol1 = 150
            tol2 = -250
            p = self.tmp[5]
            q = self.tmp[6]
            r = self.tmp[7]

        elif roll > 5: # "+90"
            tol1 = 150
            tol2 = -250
            p = self.tmp[5]
            q = self.tmp[6]
            r = self.tmp[7]

        else: # "0"
            tol1 = 150
            tol2 = -250
            p = self.tmp[9]
            q = self.tmp[10]
            r = self.tmp[11]

        return self.orientationTest(p, q, r, tol1, tol2)


    def orientationTest(self, p: float, q: float, r: float, tol1: float, tol2: float) -> float:
        """
        Compute orientation test of three points with this sequence: p, q, r
        There are 2 tollerances tol1, tol2
        """

        #testOnThisPhalanges = [[5,6,7], [6,7,8], [9,10,11], [10,11,12], [13,14,15], [14,15,16], [17,18,19], [18,19,20]]

        tmp = np.vstack( (p,q) )
        tmp = np.vstack((tmp,r))
        ones = np.ones( (3,1) )
        tmp = np.hstack( (ones,tmp) )

        res = np.linalg.det(tmp)

       # this is a quadratic form, more stable to zero
        if res < 0:
            res = (res**2) / 1666 # 180 is empirically computed
        else:
            res = -(res**2) / 1666

        # the part above 90 degrees scale a lot
        if res < - 90:
            res = -90 - (res + 90) * 0.1
        elif res > 90:
            res = 90 + (res - 90) * 0.1
            
        return res


    def computePitch(self) -> float:
        """
        Compute pitch.
        """

        thumb_tip  = self.tmp[4]
        index_finger_mcp = self.tmp[5]
        index_finger_pip = self.tmp[6]

        # Compute the difference from the mean between index_finger_mcp and index_finger_pip with the thumb_tip y value
        pointZero = (index_finger_mcp[1] + index_finger_pip[1]) / 2
        res = pointZero - thumb_tip[1]

        # This is a quadratic form, more stable to zero
        if res < 0:
            res = (res**2) / 31 # 180 is empirically computed
        else:
            res = -(res**2) / 31

        # The part above 90 degrees scale a lot
        if res < - 90:
            res = -90 - (res + 90) * 0.1
        elif res > 90:
            res = 90 + (res - 90) * 0.1

        return res

    
    def drawOrientationVector(self, img: np.array, roll: float, yaw: float, pitch: float):
        """
        Draw the orientation vector based on middle_finger_tip and wrist points.
        """

        wrist = np.array(self.lmList[0], dtype=np.int32) # palmo
        middle_finger_tip = np.array(self.lmList[12], dtype=np.int32) # punta medio

        # Compute the vector that pass at the center
        centerVector = 1.2 * ( middle_finger_tip - wrist )

        centerVectorEnd = wrist + centerVector
        centerVectorEnd = ( int(centerVectorEnd[1]), int(centerVectorEnd[2]) )
        centerVectorStart = (wrist[1], wrist[2])
        cv2.arrowedLine(img, centerVectorStart, centerVectorEnd, (220, 25, 6), thickness=2, line_type=cv2.LINE_AA, shift=0, tipLength=0.3)

        fontScale = 0.5
        font = cv2.FONT_HERSHEY_DUPLEX
        thickness = 2
        cv2.putText(img, f"Roll: {roll}", (centerVectorEnd[0]+20,centerVectorEnd[1]), font, fontScale, (0, 225, 0), thickness)
        cv2.putText(img, f"Yaw: {yaw}", (centerVectorEnd[0]+20,centerVectorEnd[1]+40), font, fontScale, (0, 225, 0), thickness)
        cv2.putText(img, f"Pitch: {pitch}", (centerVectorEnd[0]+20,centerVectorEnd[1]+80), font, fontScale, (0, 225, 0), thickness)
        cv2.putText(img, f"MODULE: {self.zcoord}", (centerVectorEnd[0]+20,centerVectorEnd[1]+120), font, fontScale, (0, 225, 0), thickness)


    def addHomogeneousCoordinate(self):
        """
        Add homogeneous coordinate in the landmarks points.
        """
        self.tmp = np.hstack( (self.tmp, np.ones((21,1)) ))


    def removeHomogeneousCoordinate(self):
        """
        Remove homogeneous coordinate in the landmarks points.
        """

        if self.tmp.shape[1] == 3:
            self.tmp = self.tmp[:,:-1]


    def scaleLittle(self):
        self.tmp[:,:-1] = self.tmp[:,:-1] * 100


    def drawAllHandTransformed(self, img: np.array):
        """
        Draw all the point that defines the hand after the normalization in the window.
        """

        ##########################################
        # DRAW VARIABLE HAND
        ##########################################

        # Scale a bit to draw points on canvas
        tmp = self.tmp

        tmp = self.transf.translate(tmp, 130, -350) #stmp + mean + np.array([-300, 0])

        tmp = tmp[:,:-1]
        tmp[:,1] = self.height - tmp[:,1]
        tmp = tmp.astype(int)

        # DrawPoint
        fontScale = 0.3
        font = cv2.FONT_HERSHEY_DUPLEX
        thickness = 1
        color = (255,255,0)
        for i in range(tmp.shape[0]):
            position = tuple(tmp[i])
            cv2.circle(img, position, radius=0, color=color, thickness=5)
            cv2.putText(img, str(i), (position[0]+10, position[1]), font, fontScale, color, thickness)

        # Put text on thumb_tip, index_finger_mcp and index_finger_pip
        color = (0,255,0)
        position = tuple(tmp[4])
        cv2.circle(img, position, radius=0, color=color, thickness=5)
        cv2.putText(img, "thumb_tip", ( position[0] + 10, position[1] ), font, fontScale, color, thickness)
        position = tuple(tmp[5])
        cv2.circle(img, position, radius=0, color=color, thickness=5)
        cv2.putText(img, "index_finger_mcp", ( position[0] + 10, position[1] ), font, fontScale, color, thickness)
        position = tuple(tmp[6])
        cv2.circle(img, position, radius=0, color=color, thickness=5)
        cv2.putText(img, "index_finger_pip", ( position[0] + 10, position[1] ), font, fontScale, color, thickness)

        # Connect points to get the hand shape
        color = (0,0,255)
        cv2.line(img, tuple(tmp[0]), tuple(tmp[1]), color, thickness=1)
        cv2.line(img, tuple(tmp[0]), tuple(tmp[5]), color, thickness=1)
        cv2.line(img, tuple(tmp[0]), tuple(tmp[17]), color, thickness=1)
        cv2.line(img, tuple(tmp[1]), tuple(tmp[2]), color, thickness=1)
        cv2.line(img, tuple(tmp[2]), tuple(tmp[3]), color, thickness=1)
        cv2.line(img, tuple(tmp[3]), tuple(tmp[4]), color, thickness=1)
        cv2.line(img, tuple(tmp[5]), tuple(tmp[6]), color, thickness=1)
        cv2.line(img, tuple(tmp[5]), tuple(tmp[9]), color, thickness=1)
        cv2.line(img, tuple(tmp[6]), tuple(tmp[7]), color, thickness=1)
        cv2.line(img, tuple(tmp[7]), tuple(tmp[8]), color, thickness=1)
        cv2.line(img, tuple(tmp[9]), tuple(tmp[10]), color, thickness=1)
        cv2.line(img, tuple(tmp[9]), tuple(tmp[13]), color, thickness=1)
        cv2.line(img, tuple(tmp[10]), tuple(tmp[11]), color, thickness=1)
        cv2.line(img, tuple(tmp[11]), tuple(tmp[12]), color, thickness=1)
        cv2.line(img, tuple(tmp[13]), tuple(tmp[14]), color, thickness=1)
        cv2.line(img, tuple(tmp[14]), tuple(tmp[15]), color, thickness=1)
        cv2.line(img, tuple(tmp[15]), tuple(tmp[16]), color, thickness=1)
        cv2.line(img, tuple(tmp[13]), tuple(tmp[17]), color, thickness=1)
        cv2.line(img, tuple(tmp[17]), tuple(tmp[18]), color, thickness=1)
        cv2.line(img, tuple(tmp[18]), tuple(tmp[19]), color, thickness=1)
        cv2.line(img, tuple(tmp[19]), tuple(tmp[20]), color, thickness=1)


    def drawFixedHand(self, img: np.array, roll, yaw, pitch):
        ##########################################
        # FIXED FIRST HAND
        ##########################################

        # Scale a bit to draw points on canvas
        tmp = copy.deepcopy(self.firstHandNotScaled)
        tmp = self.transf.scaleMaxDistance(tmp)    

        tmp = self.transf.rotatate3D(tmp, roll, yaw, pitch)

        tmp[:,:-1] = tmp[:,:-1] * 100
        tmp = self.transf.translate(tmp, 130, -100) #stmp + mean + np.array([-300, 0])

        tmp = tmp[:,:-1]
        tmp[:,1] = self.height - tmp[:,1]
        tmp = tmp.astype(int)

        # DrawPoint
        fontScale = 0.3
        font = cv2.FONT_HERSHEY_DUPLEX
        thickness = 1
        color = (255,255,0)
        for i in range(tmp.shape[0]):
            position = tuple(tmp[i])
            cv2.circle(img, position, radius=0, color=color, thickness=5)
            cv2.putText(img, str(i), (position[0]+10, position[1]), font, fontScale, color, thickness)

        # Put text on thumb_tip, index_finger_mcp and index_finger_pip
        color = (0,255,0)
        position = tuple(tmp[4])
        cv2.circle(img, position, radius=0, color=color, thickness=5)
        cv2.putText(img, "thumb_tip", ( position[0] + 10, position[1] ), font, fontScale, color, thickness)
        position = tuple(tmp[5])
        cv2.circle(img, position, radius=0, color=color, thickness=5)
        cv2.putText(img, "index_finger_mcp", ( position[0] + 10, position[1] ), font, fontScale, color, thickness)
        position = tuple(tmp[6])
        cv2.circle(img, position, radius=0, color=color, thickness=5)
        cv2.putText(img, "index_finger_pip", ( position[0] + 10, position[1] ), font, fontScale, color, thickness)

        # Connect points to get the hand shape
        color = (0,0,255)
        cv2.line(img, tuple(tmp[0]), tuple(tmp[1]), color, thickness=1)
        cv2.line(img, tuple(tmp[0]), tuple(tmp[5]), color, thickness=1)
        cv2.line(img, tuple(tmp[0]), tuple(tmp[17]), color, thickness=1)
        cv2.line(img, tuple(tmp[1]), tuple(tmp[2]), color, thickness=1)
        cv2.line(img, tuple(tmp[2]), tuple(tmp[3]), color, thickness=1)
        cv2.line(img, tuple(tmp[3]), tuple(tmp[4]), color, thickness=1)
        cv2.line(img, tuple(tmp[5]), tuple(tmp[6]), color, thickness=1)
        cv2.line(img, tuple(tmp[5]), tuple(tmp[9]), color, thickness=1)
        cv2.line(img, tuple(tmp[6]), tuple(tmp[7]), color, thickness=1)
        cv2.line(img, tuple(tmp[7]), tuple(tmp[8]), color, thickness=1)
        cv2.line(img, tuple(tmp[9]), tuple(tmp[10]), color, thickness=1)
        cv2.line(img, tuple(tmp[9]), tuple(tmp[13]), color, thickness=1)
        cv2.line(img, tuple(tmp[10]), tuple(tmp[11]), color, thickness=1)
        cv2.line(img, tuple(tmp[11]), tuple(tmp[12]), color, thickness=1)
        cv2.line(img, tuple(tmp[13]), tuple(tmp[14]), color, thickness=1)
        cv2.line(img, tuple(tmp[14]), tuple(tmp[15]), color, thickness=1)
        cv2.line(img, tuple(tmp[15]), tuple(tmp[16]), color, thickness=1)
        cv2.line(img, tuple(tmp[13]), tuple(tmp[17]), color, thickness=1)
        cv2.line(img, tuple(tmp[17]), tuple(tmp[18]), color, thickness=1)
        cv2.line(img, tuple(tmp[18]), tuple(tmp[19]), color, thickness=1)
        cv2.line(img, tuple(tmp[19]), tuple(tmp[20]), color, thickness=1)


    def computeDepth(self, roll, yaw, pitch):
        """
        Compute distance from wrist to middle finger tip.
        """

        tmp = copy.deepcopy(self.firstHandNotScaled)
        
        # Transform the first hand in order to have the same orientation in the space
        tmp = self.transf.rotatate3D(tmp, roll, yaw, pitch)

        # Copmute distance of each point from the center
        sum_dist_orig = np.mean(np.sqrt(tmp[:,0]**2 + tmp[:,1]**2))
        sum_dist_new = np.mean(np.sqrt(self.currentHandNotScaled[:,0]**2 + self.currentHandNotScaled[:,1]**2))
        
        # Compute the differences between this two values to 
        # estimate the depth
        diff = sum_dist_new - sum_dist_orig
        
        self.zcoord = np.mean(diff)