import rospy
import numpy
import math
from gym import spaces
from openai_ros.robot_envs import turtlebot2_env
from gym.envs.registration import register
from geometry_msgs.msg import Point
from cv_bridge import CvBridge
bridge = CvBridge()

timestep_limit_per_episode = 10000 # Can be any Value

register(
        id='MyTurtleBot2Wall-v1',
        entry_point='openai_ros.task_envs.turtlebot2.turtlebot2_maze:TurtleBot2MazeEnv',
        timestep_limit=timestep_limit_per_episode,
    )

class TurtleBot2MazeEnv(turtlebot2_env.TurtleBot2Env):
    def __init__(self):
        """
        This Task Env is designed for having the TurtleBot2 in some kind of maze.
        It will learn how to move around the maze without crashing.
        """
        
        # Only variable needed to be set here
        number_actions = rospy.get_param('/turtlebot2/n_actions')

        self.action_space = spaces.Discrete(number_actions)
        
        # We set the reward range, which is not compulsory but here we do it.
        self.reward_range = (-numpy.inf, numpy.inf)
        
        
        self.number_observations = rospy.get_param('/turtlebot2/n_observations')
        """
        We set the Observation space for the 6 observations
        cube_observations = [
            round(current_disk_roll_vel, 0),
            round(y_distance, 1),
            round(roll, 1),
            round(pitch, 1),
            round(y_linear_speed,1),
            round(yaw, 1),
        ]
        """
        #Actions and Observations
        self.linear_forward_speed = rospy.get_param('/turtlebot2/linear_forward_speed')
        self.linear_turn_speed = rospy.get_param('/turtlebot2/linear_turn_speed')
        self.angular_speed = rospy.get_param('/turtlebot2/angular_speed')
        self.init_linear_forward_speed = rospy.get_param('/turtlebot2/init_linear_forward_speed')
        self.init_linear_turn_speed = rospy.get_param('/turtlebot2/init_linear_turn_speed')
        
        self.new_ranges = rospy.get_param('/turtlebot2/new_ranges')
        
        self.min_range = rospy.get_param('/turtlebot2/min_range')
        self.max_laser_value = rospy.get_param('/turtlebot2/max_laser_value')
        self.min_laser_value = rospy.get_param('/turtlebot2/min_laser_value')
        
        # Get Desired Point to Get
        self.desired_point = Point()
        self.desired_point.x = rospy.get_param("/turtlebot2/desired_pose/x")
        self.desired_point.y = rospy.get_param("/turtlebot2/desired_pose/y")
        self.desired_point.z = rospy.get_param("/turtlebot2/desired_pose/z")
        
        # We create two arrays based on the binary values that will be assigned
        # In the discretization method.
        laser_scan = self._check_laser_scan_ready()
        image_read = self._check_camera_rgb_image_raw_ready()
        #self.new_ranges = int(math.ceil(float(len(laser_scan.ranges)) / float(self.number_observations)))
        num_laser_readings = len(laser_scan.ranges)/self.new_ranges
        cv2_img = bridge.imgmsg_to_cv2(image_read, "bgr8")
        height, width, channels = cv2_img.shape



        # high = numpy.full((num_laser_readings), self.max_laser_value)
        # low = numpy.full((num_laser_readings), self.min_laser_value)
        high = numpy.full((self.number_observations), self.max_laser_value)
        low = numpy.full((self.number_observations), self.min_laser_value)
        # We only use two integers
        #self.observation_space = spaces.Box(low, high)
        self.observation_space = spaces.Box(low=0, high=255, shape=(height, width, channels), dtype=numpy.uint8)

        rospy.logdebug("ACTION SPACES TYPE===>"+str(self.action_space))
        rospy.logdebug("OBSERVATION SPACES TYPE===>"+str(self.observation_space))
        
        # Rewards
        self.forwards_reward = rospy.get_param("/turtlebot2/forwards_reward")
        self.turn_reward = rospy.get_param("/turtlebot2/turn_reward")
        self.end_episode_points = rospy.get_param("/turtlebot2/end_episode_points")
        self.distance_reward = rospy.get_param("/turtlebot2/distance_reward")





        self.cumulated_steps = 0.0

        # Here we will add any init functions prior to starting the MyRobotEnv
        super(TurtleBot2MazeEnv, self).__init__()

    def _set_init_pose(self):
        """Sets the Robot in its init pose
        """
        self.move_base( self.init_linear_forward_speed,
                        self.init_linear_turn_speed,
                        epsilon=0.05,
                        update_rate=10)

        return True


    def _init_env_variables(self):
        """
        Inits variables needed to be initialised each time we reset at the start
        of an episode.
        :return:
        """
        # For Info Purposes
        self.cumulated_reward = 0.0
        # Set to false Done, because its calculated asyncronously
        self._episode_done = False
        
        odometry = self.get_odom()
        self.previous_distance_from_des_point = self.get_distance_from_desired_point(odometry.pose.pose.position)


    def _set_action(self, action):
        """
        This set action will Set the linear and angular speed of the turtlebot2
        based on the action number given.
        :param action: The action integer that set s what movement to do next.
        """
        
        rospy.logdebug("Start Set Action ==>"+str(action))
        # We convert the actions to speed movements to send to the parent class CubeSingleDiskEnv
        if action == 0: #FORWARD
            linear_speed = self.linear_forward_speed
            angular_speed = 0.0
            self.last_action = "FORWARDS"
        elif action == 1: #LEFT
            linear_speed = self.linear_turn_speed
            angular_speed = self.angular_speed
            self.last_action = "TURN_LEFT"
        elif action == 2: #RIGHT
            linear_speed = self.linear_turn_speed
            angular_speed = -1*self.angular_speed
            self.last_action = "TURN_RIGHT"

        
        # We tell TurtleBot2 the linear and angular speed to set to execute
        self.move_base(linear_speed, angular_speed, epsilon=0.05, update_rate=10)
        
        rospy.logdebug("END Set Action ==>"+str(action))

    def _get_obs(self):
        """
        Here we define what sensor data defines our robots observations
        To know which Variables we have acces to, we need to read the
        TurtleBot2Env API DOCS
        :return:
        """
        rospy.logdebug("Start Get Observation ==>")
        # We get the laser scan data
        laser_scan = self.get_laser_scan()
        
        discretized_laser_scan = self.discretize_observation( laser_scan,
                                                                self.new_ranges
                                                                )
                                                                
        # We get the odometry so that SumitXL knows where it is.
        odometry = self.get_odom()
        x_position = odometry.pose.pose.position.x
        y_position = odometry.pose.pose.position.y

        # We round to only two decimals to avoid very big Observation space
        odometry_array = [round(x_position, 2),round(y_position, 2)]                                                 


        # Get observation from Image
        image_data = self.get_camera_rgb_image_raw()
        cv2_img = bridge.imgmsg_to_cv2(image_data, "bgr8")
        height, width, channels = cv2_img.shape

        i = numpy.array(cv2_img)
        
        #image_flatten = list(i.flatten())

        #ob_test = numpy.concatenate(discretized_laser_scan, image_flatten)

        

        #observations = discretized_laser_scan + odometry_array
        observations = i

        rospy.logdebug("Observations==>"+str(observations))
        rospy.logdebug("END Get Observation ==>")
        return observations
        

    def _is_done(self, observations):
            # We get the odometry so that SumitXL knows where it is.
        odometry = self.get_odom()
        x_position = odometry.pose.pose.position.x
        y_position = odometry.pose.pose.position.y

        # We round to only two decimals to avoid very big Observation space
        odometry_array = [round(x_position, 2),round(y_position, 2)]

        # We only want the X and Y position and the Yaw
        
        if self._episode_done:
            rospy.logerr("TurtleBot2 is Too Close to wall==>")
        else:
            rospy.logerr("TurtleBot2 didnt crash at least ==>")
       
       
            current_position = Point()
            current_position.x = odometry_array[0]
            current_position.y = odometry_array[1]
            current_position.z = 0.0
            
            MAX_X = 15.0
            MIN_X = -15.0
            MAX_Y = 15.0
            MIN_Y = -15.0
            
            # We see if we are outside the Learning Space
            
            if current_position.x <= MAX_X and current_position.x > MIN_X:
                if current_position.y <= MAX_Y and current_position.y > MIN_Y:
                    rospy.logdebug("TurtleBot Position is OK ==>["+str(current_position.x)+","+str(current_position.y)+"]")
                    
                    # We see if it got to the desired point
                    if self.is_in_desired_position(current_position):
                        self._episode_done = True
                    
                    
                else:
                    rospy.logerr("TurtleBot to Far in Y Pos ==>"+str(current_position.x))
                    self._episode_done = True
            else:
                rospy.logerr("TurtleBot to Far in X Pos ==>"+str(current_position.x))
                self._episode_done = True
            
            
            

        return self._episode_done

    # def _compute_reward(self, observations, done):
    #     # We get the odometry so that SumitXL knows where it is.
    #     odometry = self.get_odom()
    #     x_position = odometry.pose.pose.position.x
    #     y_position = odometry.pose.pose.position.y

    #     # We round to only two decimals to avoid very big Observation space
    #     odometry_array = [round(x_position, 2),round(y_position, 2)]

    #     # We only want the X and Y position and the Yaw
        

    #     current_position = Point()
    #     current_position.x = odometry_array[0]
    #     current_position.y = odometry_array[1]
    #     current_position.z = 0.0

    #     distance_from_des_point = self.get_distance_from_desired_point(current_position)
    #     distance_difference =  distance_from_des_point - self.previous_distance_from_des_point


    #     if not done:
            
    #         if self.last_action == "FORWARDS":
    #             reward = self.forwards_reward
    #         else:
    #             reward = self.turn_reward
                
    #         # If there has been a decrease in the distance to the desired point, we reward it

    #         # If the distance from desired point decrease -> (+) reward 
    #         if distance_difference < 0.0:
    #             rospy.logwarn("DECREASE IN DISTANCE GOOD")
    #             reward += self.distance_reward
    #         else:
    #             rospy.logerr("ENCREASE IN DISTANCE BAD")
    #             reward += 0
                
    #     else:
            
    #         if self.is_in_desired_position(current_position): # If current position coincides with the desired point then return True 
    #                                                           # and get (+) value
    #             reward = self.end_episode_points
    #         else:
    #             reward = -1*self.end_episode_points


    #     self.previous_distance_from_des_point = distance_from_des_point


    #     rospy.logdebug("reward=" + str(reward))
    #     self.cumulated_reward += reward
    #     rospy.logdebug("Cumulated_reward=" + str(self.cumulated_reward))
    #     self.cumulated_steps += 1
    #     rospy.logdebug("Cumulated_steps=" + str(self.cumulated_steps))
        
    #     return reward

    def _compute_reward(self, observations, done):
        # We get the odometry so that SumitXL knows where it is.
        odometry = self.get_odom()
        x_position = odometry.pose.pose.position.x
        y_position = odometry.pose.pose.position.y

        # We round to only two decimals to avoid very big Observation space
        odometry_array = [round(x_position, 2),round(y_position, 2)]

        # We only want the X and Y position and the Yaw
        

        current_position = Point()
        current_position.x = odometry_array[0]
        current_position.y = odometry_array[1]
        current_position.z = 0.0

        distance_from_des_point = self.get_distance_from_desired_point(current_position)
        distance_difference =  distance_from_des_point - self.previous_distance_from_des_point

        orientation_robot_to_goal = math.atan2(self.desired_point.y - current_position.y, self.desired_point.x - current_position.x)
        orientation_robot = math.atan2(current_position.y,current_position.x)
        diff = self.difference_two_angles(orientation_robot_to_goal,orientation_robot)
        r_orientation = (math.pi-math.fabs(diff))/math.pi

        #reward = 0.0


        if not done:
            
            if self.last_action == "FORWARDS":
                reward = self.forwards_reward
            else:
                reward = self.turn_reward
                
            # If there has been a decrease in the distance to the desired point, we reward it

            # If the distance from desired point decrease -> (+) reward 
            if distance_difference < 0.0:
                rospy.logwarn("DECREASE IN DISTANCE GOOD")
                distance_difference *= 1.5
            else:
                rospy.logerr("ENCREASE IN DISTANCE BAD")
                distance_difference *= 2

            reward += -1*distance_difference + r_orientation
                
        else:
            
            if self.is_in_desired_position(current_position): # If current position coincides with the desired point then return True 
                                                              # and get (+) value
                reward = self.end_episode_points
            else:
                reward = -1*self.end_episode_points


        self.previous_distance_from_des_point = distance_from_des_point


        rospy.logdebug("reward=" + str(reward))
        self.cumulated_reward += reward
        rospy.logdebug("Cumulated_reward=" + str(self.cumulated_reward))
        self.cumulated_steps += 1
        rospy.logdebug("Cumulated_steps=" + str(self.cumulated_steps))
        
        return reward
        
    def difference_two_angles(self,angle1, angle2):
        diff = (angle1 - angle2) % (math.pi * 2)
        if diff >= math.pi:
            diff -= math.pi * 2
        return diff
    # Internal TaskEnv Methods
    
    def discretize_observation(self,data,new_ranges):
        """
        Discards all the laser readings that are not multiple in index of new_ranges
        value.
        """
        self._episode_done = False
        
        discretized_ranges = []
        mod = len(data.ranges)/new_ranges
        
        rospy.logdebug("data=" + str(data))
        rospy.logwarn("new_ranges=" + str(new_ranges))
        rospy.logwarn("mod=" + str(mod))
        
        for i, item in enumerate(data.ranges):
            if (i%mod==0):
                if item == float ('Inf') or numpy.isinf(item):
                    discretized_ranges.append(self.max_laser_value)
                elif numpy.isnan(item):
                    discretized_ranges.append(self.min_laser_value)
                else:
                    discretized_ranges.append(int(item))
                    
                if (self.min_range > item > 0):
                    rospy.logerr("Done Validation >>> item=" + str(item)+"< "+str(self.min_range))
                    self._episode_done = True
                else:
                    rospy.logwarn("NOT done Validation >>> item=" + str(item)+"< "+str(self.min_range))
                    

        return discretized_ranges
        
        
    def is_in_desired_position(self,current_position, epsilon=0.2):    #0.05
        """
        It return True if the current position is similar to the desired poistion
        """
        
        is_in_desired_pos = False
        
        
        x_pos_plus = self.desired_point.x + epsilon
        x_pos_minus = self.desired_point.x - epsilon
        y_pos_plus = self.desired_point.y + epsilon
        y_pos_minus = self.desired_point.y - epsilon
        
        x_current = current_position.x
        y_current = current_position.y
        
        x_pos_are_close = (x_current <= x_pos_plus) and (x_current > x_pos_minus)
        y_pos_are_close = (y_current <= y_pos_plus) and (y_current > y_pos_minus)
        
        is_in_desired_pos = x_pos_are_close and y_pos_are_close
        
        return is_in_desired_pos
        
        
    def get_distance_from_desired_point(self, current_position):
        """
        Calculates the distance from the current position to the desired point
        :param start_point:
        :return:
        """
        distance = self.get_distance_from_point(current_position,
                                                self.desired_point)
    
        return distance
    
    def get_distance_from_point(self, pstart, p_end):
        """
        Given a Vector3 Object, get distance from current position
        :param p_end:
        :return:
        """
        a = numpy.array((pstart.x, pstart.y, pstart.z))
        b = numpy.array((p_end.x, p_end.y, p_end.z))
    
        distance = numpy.linalg.norm(a - b)
    
        return distance

