# videomodule.VideoThread()
    def old_emit_pixmap(self, frame):
        # Convert frame to QPixmap for display
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt_format = QImage(rgb_image.data, w, h, bytes_per_line,
                                      QImage.Format.Format_RGB888)
        p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
        self.change_pixmap_signal.emit(QPixmap.fromImage(p))
        
# videomodule.VideoThreadTracking()
    def process_frame(self, frame):
        max_value = 255
        inverted_frame = cv2.bitwise_not(frame)
        #inverted_frame = cv2.blur(inverted_frame, (5, 5))
        ret, binary_frame = cv2.threshold(inverted_frame, max_value-self.threshold,
                                          max_value, cv2.THRESH_BINARY) # + cv2.THRESH_OTSU)
        contours, hierarchy = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        centroid = ()
        largest_area = 0
        largest_contour = None

        if contours:
            #print('----------------------------------')
            for indc, cnt in enumerate(contours):
                area = cv2.contourArea(cnt)
                #cv2.drawContours(frame, [cnt], -1, (255, 255, 255), 2) # White contour
                #print(f"{indc}: {area}")
                if area > largest_area:
                    largest_area = area
                    largest_contour = cnt
            if largest_contour is not None and largest_area > AREA_THRESHOLD:
                mom = cv2.moments(largest_contour)
                if mom["m00"] != 0:
                    cX = int(mom["m10"] / mom["m00"])
                    cY = int(mom["m01"] / mom["m00"])
                    centroid = (cX, cY)

                    # Optional: Draw the contour and centroid
                    #if self.mode == 'grayscale':
                    #    cv2.drawContours(frame, [largest_contour], -1, (255, 255, 255), 2)
                    #cv2.drawContours(frame, [largest_contour], -1, (255, 255, 255), 4)
                    #cv2.circle(frame, centroid, 5, (255, 255, 255), -1) # Red centroid
                    #cv2.putText(frame, f"({cX},{cY}: {largest_area})",
                    #            (cX + 10, cY + 10),
                    #            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                #print(f"*{indc}* : {largest_area}")
        # Emit the processed frame and the centroid coordinates
        if self.mode == 'grayscale':
            self.frame_processed.emit(frame, centroid)
        elif self.mode == 'binary':
            self.frame_processed.emit(cv2.bitwise_not(binary_frame), centroid)
        
