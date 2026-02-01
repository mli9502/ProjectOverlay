"""
Video Overlay Generator GUI
Cross-platform (Windows, Mac, Linux) application using PyQt6
"""
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QSlider, QCheckBox, QGroupBox,
    QScrollArea, QProgressBar, QFrame, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage
import numpy as np
from PIL import Image
import pandas as pd

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.extract import parse_fit
from src.overlay import create_frame_rgba

# Default overlay config
DEFAULT_CONFIG = {
    'speed': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
    'power': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
    'cadence': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
    'gradient': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
    'map': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
    'elevation': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
}


class ComponentControl(QGroupBox):
    """Control widget for a single overlay component"""
    changed = pyqtSignal()
    
    def __init__(self, name: str, display_name: str):
        super().__init__(display_name)
        self.name = name
        self.setCheckable(True)
        self.setChecked(True)
        
        layout = QVBoxLayout()
        
        # Size slider
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(50, 200)
        self.size_slider.setValue(100)
        self.size_label = QLabel("100%")
        self.size_slider.valueChanged.connect(self._on_size_changed)
        size_layout.addWidget(self.size_slider)
        size_layout.addWidget(self.size_label)
        layout.addLayout(size_layout)
        
        # Opacity slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        layout.addLayout(opacity_layout)
        
        self.setLayout(layout)
        
        # Connect toggle
        self.toggled.connect(lambda: self.changed.emit())
        
    def _on_size_changed(self, value):
        self.size_label.setText(f"{value}%")
        self.changed.emit()
        
    def _on_opacity_changed(self, value):
        self.opacity_label.setText(f"{value}%")
        self.changed.emit()
        
    def get_config(self):
        return {
            'enabled': self.isChecked(),
            'scale': self.size_slider.value() / 100.0,
            'opacity': self.opacity_slider.value() / 100.0,
        }


class PreviewWidget(QLabel):
    """Widget to display the overlay preview"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333;")
        self.setText("Load a video and FIT file to preview")
        
    def update_preview(self, pil_image: Image.Image):
        """Update the preview with a PIL image"""
        # Convert PIL to QPixmap
        img = pil_image.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg)
        
        # Scale to fit widget while maintaining aspect ratio
        scaled = pixmap.scaled(
            self.width(), self.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)


class GenerateThread(QThread):
    """Background thread for video generation"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, video_path, fit_path, config, output_path):
        super().__init__()
        self.video_path = video_path
        self.fit_path = fit_path
        self.config = config
        self.output_path = output_path
        
    def run(self):
        try:
            # Import here to avoid circular imports
            from src.main import main as generate_video
            
            # For now, use the existing main function
            # TODO: Integrate config into generation pipeline
            self.progress.emit(10, "Parsing FIT file...")
            
            # This is a placeholder - will integrate properly
            self.progress.emit(50, "Generating video...")
            
            # TODO: Call the actual generation with config
            self.progress.emit(100, "Complete!")
            self.finished.emit(self.output_path)
            
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Overlay Generator")
        self.setMinimumSize(1200, 800)
        
        # State
        self.video_path = None
        self.fit_path = None
        self.fit_data = None
        self.preview_debounce = QTimer()
        self.preview_debounce.setSingleShot(True)
        self.preview_debounce.timeout.connect(self._update_preview)
        
        self._setup_ui()
        
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        
        # Left panel - controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(350)
        
        # File selection
        file_group = QGroupBox("Files")
        file_layout = QVBoxLayout()
        
        # Video file
        video_layout = QHBoxLayout()
        self.video_label = QLabel("No video selected")
        self.video_label.setWordWrap(True)
        video_btn = QPushButton("Browse Video...")
        video_btn.clicked.connect(self._browse_video)
        video_layout.addWidget(self.video_label, 1)
        video_layout.addWidget(video_btn)
        file_layout.addLayout(video_layout)
        
        # FIT file
        fit_layout = QHBoxLayout()
        self.fit_label = QLabel("No FIT file selected")
        self.fit_label.setWordWrap(True)
        fit_btn = QPushButton("Browse FIT...")
        fit_btn.clicked.connect(self._browse_fit)
        fit_layout.addWidget(self.fit_label, 1)
        fit_layout.addWidget(fit_btn)
        file_layout.addLayout(fit_layout)
        
        file_group.setLayout(file_layout)
        left_layout.addWidget(file_group)
        
        # Component controls
        components_group = QGroupBox("Overlay Components")
        components_layout = QVBoxLayout()
        
        self.component_controls = {}
        components = [
            ('speed', 'Speed (MPH)'),
            ('power', 'Power (W)'),
            ('cadence', 'Cadence (RPM)'),
            ('gradient', 'Gradient (%)'),
            ('map', 'Mini Map'),
            ('elevation', 'Elevation Profile'),
        ]
        
        for name, display in components:
            ctrl = ComponentControl(name, display)
            ctrl.changed.connect(self._schedule_preview_update)
            self.component_controls[name] = ctrl
            components_layout.addWidget(ctrl)
            
        components_group.setLayout(components_layout)
        
        # Scroll area for components
        scroll = QScrollArea()
        scroll.setWidget(components_group)
        scroll.setWidgetResizable(True)
        left_layout.addWidget(scroll, 1)
        
        # Generate button
        self.generate_btn = QPushButton("Generate Video")
        self.generate_btn.setMinimumHeight(50)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._generate_video)
        left_layout.addWidget(self.generate_btn)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)
        
        main_layout.addWidget(left_panel)
        
        # Right panel - preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        preview_label = QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(preview_label)
        
        self.preview = PreviewWidget()
        right_layout.addWidget(self.preview, 1)
        
        # Preview time slider
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Preview Time:"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.setValue(0)
        self.time_slider.valueChanged.connect(self._schedule_preview_update)
        self.time_label = QLabel("0:00")
        time_layout.addWidget(self.time_slider)
        time_layout.addWidget(self.time_label)
        right_layout.addLayout(time_layout)
        
        main_layout.addWidget(right_panel, 1)
        
    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.MP4 *.mov *.MOV *.avi *.AVI);;All Files (*)"
        )
        if path:
            self.video_path = path
            self.video_label.setText(Path(path).name)
            self._check_ready()
            self._schedule_preview_update()
            
    def _browse_fit(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FIT File", "",
            "FIT Files (*.fit *.FIT);;All Files (*)"
        )
        if path:
            self.fit_path = path
            self.fit_label.setText(Path(path).name)
            try:
                self.fit_data = parse_fit(path)
                duration = len(self.fit_data)
                self.time_slider.setRange(0, duration - 1)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to parse FIT file: {e}")
                return
            self._check_ready()
            self._schedule_preview_update()
            
    def _check_ready(self):
        ready = self.video_path is not None and self.fit_path is not None
        self.generate_btn.setEnabled(ready)
        
    def _schedule_preview_update(self):
        # Debounce preview updates
        self.preview_debounce.start(100)
        
    def _update_preview(self):
        if self.fit_data is None:
            return
            
        try:
            # Get current config
            config = {name: ctrl.get_config() for name, ctrl in self.component_controls.items()}
            
            # Get data for current time
            time_idx = self.time_slider.value()
            if time_idx >= len(self.fit_data):
                time_idx = len(self.fit_data) - 1
                
            # Update time label
            minutes = time_idx // 60
            seconds = time_idx % 60
            self.time_label.setText(f"{minutes}:{seconds:02d}")
            
            row = self.fit_data.iloc[time_idx]
            row_dict = row.to_dict()
            row_dict['full_track_df'] = self.fit_data
            
            # Generate frame with config
            # For now, use default size; TODO: get from video metadata
            frame = create_frame_rgba(time_idx, row_dict, 1920, 1080, config=config)
            self.preview.update_preview(frame)
            
        except Exception as e:
            print(f"Preview error: {e}")
            
    def _get_config(self):
        return {name: ctrl.get_config() for name, ctrl in self.component_controls.items()}
        
    def _generate_video(self):
        if not self.video_path or not self.fit_path:
            return
            
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Video As", "output.mp4",
            "MP4 Files (*.mp4);;All Files (*)"
        )
        if not output_path:
            return
            
        config = self._get_config()
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.generate_btn.setEnabled(False)
        
        self.gen_thread = GenerateThread(
            self.video_path, self.fit_path, config, output_path
        )
        self.gen_thread.progress.connect(self._on_progress)
        self.gen_thread.finished.connect(self._on_finished)
        self.gen_thread.error.connect(self._on_error)
        self.gen_thread.start()
        
    def _on_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.statusBar().showMessage(message)
        
    def _on_finished(self, path):
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        QMessageBox.information(self, "Success", f"Video saved to:\n{path}")
        
    def _on_error(self, message):
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Generation failed:\n{message}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Cross-platform consistent style
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
