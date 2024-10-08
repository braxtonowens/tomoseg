import sys
import os
import numpy as np
import mrcfile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QAction, QFileDialog, QToolBar,
    QMessageBox, QSpinBox, QScrollArea
)
from PyQt5.QtGui import QPixmap, QPainter, QPen, QImage, QColor
from PyQt5.QtCore import Qt, QPoint, QSize

class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points_foreground = []
        self.points_background = []
        self.current_mode = 'foreground'  # or 'background'
        self.image = QPixmap()
        self.setMouseTracking(True)
        self.point_size = 5

    def set_image(self, image_path, max_size=None):
        self.image = QPixmap(image_path)
        if max_size:
            self.image = self.image.scaled(max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(self.image)
        self.setFixedSize(self.image.size())
        self.points_foreground = []
        self.points_background = []

    def set_mrc_image(self, pixmap, max_size=None):
        if max_size:
            pixmap = pixmap.scaled(max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image = pixmap
        self.setPixmap(self.image)
        self.setFixedSize(self.image.size())
        self.points_foreground = []
        self.points_background = []

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen()
        pen.setWidth(2)
        for point in self.points_foreground:
            pen.setColor(Qt.green)
            painter.setPen(pen)
            painter.drawEllipse(point, self.point_size, self.point_size)
        for point in self.points_background:
            pen.setColor(Qt.blue)
            painter.setPen(pen)
            painter.drawEllipse(point, self.point_size, self.point_size)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.current_mode == 'foreground':
                self.points_foreground.append(event.pos())
            elif self.current_mode == 'background':
                self.points_background.append(event.pos())
            self.update()
        elif event.button() == Qt.RightButton:
            self.remove_point(event.pos())
            self.update()

    def remove_point(self, pos):
        radius = self.point_size + 2
        for point_list in [self.points_foreground, self.points_background]:
            for point in point_list:
                if (point - pos).manhattanLength() <= radius:
                    point_list.remove(point)
                    return

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Tomoseg GUI')
        self.image_label = ImageLabel()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setAlignment(Qt.AlignCenter)  # Center the image
        self.setCentralWidget(self.scroll_area)
        self.create_actions()
        self.create_toolbar()
        self.image_label.current_mode = 'foreground'
        self.mrc_data = None
        self.mrc_filename = ''
        self.current_slice = 0
        self.total_slices = 0

        # Make the starting size of the window larger
        self.resize(1000, 800)

        # Center the window on the screen
        self.center_window()

    def center_window(self):
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def create_actions(self):
        self.open_action = QAction('Open Image/MRC', self)
        self.open_action.triggered.connect(self.open_image)

        self.foreground_action = QAction('Foreground', self)
        self.foreground_action.setCheckable(True)
        self.foreground_action.setChecked(True)
        self.foreground_action.triggered.connect(self.set_foreground_mode)

        self.background_action = QAction('Background', self)
        self.background_action.setCheckable(True)
        self.background_action.triggered.connect(self.set_background_mode)

        self.clear_action = QAction('Clear Points', self)
        self.clear_action.triggered.connect(self.clear_points)

        self.save_points_action = QAction('Save Points', self)
        self.save_points_action.triggered.connect(self.save_points)

        self.exit_action = QAction('Exit', self)
        self.exit_action.triggered.connect(self.close)

    def create_toolbar(self):
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)
        self.toolbar.addAction(self.open_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.foreground_action)
        self.toolbar.addAction(self.background_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.clear_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.save_points_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.exit_action)

    def open_image(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Open Image File', '',
            'Images and MRC Files (*.png *.jpg *.bmp *.tif *.tiff *.mrc)', options=options)
        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext == '.mrc':
                self.open_mrc_file(filename)
            else:
                self.mrc_data = None
                self.mrc_filename = ''
                # Resize the image to be slightly smaller than the window
                max_size = self.get_max_image_size()
                self.image_label.set_image(filename, max_size)
                self.image_label.adjustSize()
                self.scroll_area.setWidgetResizable(False)
                if hasattr(self, 'slice_selector'):
                    self.toolbar.removeWidget(self.slice_selector)
                    del self.slice_selector

    def open_mrc_file(self, filename):
        try:
            with mrcfile.open(filename, permissive=True) as mrc:
                self.mrc_data = mrc.data
                self.mrc_filename = filename
                self.current_slice = len(self.mrc_data)//2
                self.total_slices = self.mrc_data.shape[0] - 1
                self.show_mrc_slice(self.current_slice)
                self.create_slice_selector()
                self.scroll_area.setWidgetResizable(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open MRC file:\n{e}")

    def show_mrc_slice(self, slice_index):
        slice_data = self.mrc_data[slice_index]
        p01, p99 = np.percentile(slice_data, [1, 99])
        clipped_image = np.clip(slice_data, p01, p99)
        normalized_image = ((clipped_image - p01) / (p99 - p01)) * 255
        height, width = np.shape(normalized_image)
        image = QImage(normalized_image.astype(np.uint8), width, height, width, QImage.Format_Grayscale8)
        
        pixmap = QPixmap.fromImage(image)
        # Resize the image to be slightly smaller than the window
        max_size = self.get_max_image_size()
        self.image_label.set_mrc_image(pixmap, max_size)
        self.image_label.adjustSize()

    def create_slice_selector(self):
        if hasattr(self, 'slice_selector'):
            self.slice_selector.setMaximum(self.total_slices)
        else:
            self.slice_selector = QSpinBox()
            self.slice_selector.setMinimum(0)
            self.slice_selector.setMaximum(self.total_slices)
            self.slice_selector.setValue(self.current_slice)
            self.slice_selector.valueChanged.connect(self.slice_changed)
            self.toolbar.addWidget(self.slice_selector)

    def slice_changed(self, value):
        self.current_slice = value
        self.show_mrc_slice(self.current_slice)

    def set_foreground_mode(self):
        self.foreground_action.setChecked(True)
        self.background_action.setChecked(False)
        self.image_label.current_mode = 'foreground'

    def set_background_mode(self):
        self.foreground_action.setChecked(False)
        self.background_action.setChecked(True)
        self.image_label.current_mode = 'background'

    def clear_points(self):
        self.image_label.points_foreground = []
        self.image_label.points_background = []
        self.image_label.update()

    def save_points(self):
        if not os.path.exists('input_points'):
            os.makedirs('input_points')
        points_foreground = np.array([[p.x(), p.y()] for p in self.image_label.points_foreground])
        points_background = np.array([[p.x(), p.y()] for p in self.image_label.points_background])
        all_points = np.vstack((points_foreground, points_background))
        labels = np.hstack((
            np.ones(len(points_foreground), dtype=int),
            np.zeros(len(points_background), dtype=int)
        ))
        data_dict = {
            'filename': self.mrc_filename if self.mrc_filename else '',
            'points': all_points,
            'labels': labels
        }
        # Save the data_dict as a .npz file
        base_filename = os.path.splitext(os.path.basename(data_dict['filename']))[0]
        if not base_filename:
            base_filename = 'image'
        save_path = os.path.join('input_points', f'{base_filename}_points.npz')
        try:
            np.savez(save_path, **data_dict)
            QMessageBox.information(self, "Saved", f"Points saved to {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save points:\n{e}")

    def get_max_image_size(self):
        # Calculate the maximum size for the image, slightly smaller than the window
        window_size = self.size()
        toolbar_height = self.toolbar.sizeHint().height()
        available_width = window_size.width() - 50  # Subtract some margin
        available_height = window_size.height() - toolbar_height - 50  # Subtract some margin
        return QSize(available_width, available_height)

if __name__ == '__main__':
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())

