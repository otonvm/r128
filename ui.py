#!python3
# -*- coding: utf-8 -*-

import sys
import pathlib

from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5 import QtGui

from config import Config
conf = Config()

import logger
log = logger.Logger(__name__)
if conf.log_level:
    log.level = conf.log_level
else:
    log.level = "DEBUG"


class Signals(QtCore.QObject):
    changed = QtCore.pyqtSignal()
    accepted_drop = QtCore.pyqtSignal()


class DropFrame(QtWidgets.QLabel):
    def __init__(self, *args):
        super().__init__(*args)

        self.setFrameShape(QtWidgets.QFrame.Sunken | QtWidgets.QFrame.StyledPanel)
        self.setAcceptDrops(True)
        self.setAutoFillBackground(True)
        self.setAlignment(QtCore.Qt.AlignCenter)

        font = QtGui.QFont("Arial", 18, QtGui.QFont.Bold)
        self.setFont(font)

        self.signals = Signals()

        self.clear()

    def dragEnterEvent(self, event):
        super().activateWindow()
        super().raise_()
        if event.mimeData().hasUrls():
            if len(event.mimeData().urls()) == 1:
                self.setText("<b>DROP HERE</b>")
                self.setBackgroundRole(QtGui.QPalette.Highlight)
                event.accept()
        else:
            event.ignore()

    # def dragMoveEvent(self, event):
    #     self.setBackgroundRole(QtGui.QPalette.Highlight)
    #     event.accept()

    def dropEvent(self, event):
        self.setBackgroundRole(QtGui.QPalette.Dark)
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            path = pathlib.Path(url.toLocalFile()).absolute()
            conf.input = path
            log.d("accepted drop: {}".format(conf.input))
            event.accept()
            self.signals.accepted_drop.emit()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.clear()
        event.accept()

    @QtCore.pyqtSlot()
    def clear(self):
        self.setText("<b>DROP AREA</b>")
        self.setBackgroundRole(QtGui.QPalette.Dark)
        self.signals.changed.emit()


class Dropplet(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("R128 Normalizer")
        self.setMinimumSize(300, 400)
        self.setMaximumSize(300, 400)

        self.windowWidget = QtWidgets.QWidget(self)

        self.windowLayout = QtWidgets.QVBoxLayout()
        self.windowLayout.addStretch(1)

        self.windowWidget.setLayout(self.windowLayout)

        self.volumesLayout = QtWidgets.QVBoxLayout()
        self.volumesLayout.addStretch(1)

        self.volumesLabel = QtWidgets.QLabel(self.windowWidget)
        self.volumesLabel.setText("Normalize to:")
        self.volumesLayout.addWidget(self.volumesLabel)

        self.volumesComboBox = QtWidgets.QComboBox(self)
        self.volumesComboBox.setMinimumWidth(280)
        self._volumes_combobox_selection = None
        self._volumes_combobox_init()
        self.volumesLayout.addWidget(self.volumesComboBox)

        self.windowLayout.addLayout(self.volumesLayout)

        self.formatsGroup = QtWidgets.QGroupBox(self.windowWidget)
        self.formatsGroup.setTitle("Formats")

        self.iTunesCheckBox = QtWidgets.QCheckBox(self.windowWidget)
        self.iTunesCheckBox.setText("iTunes")

        self.aacCheckBox = QtWidgets.QCheckBox(self.windowWidget)
        self.aacCheckBox.setText("AAC")

        self.alacCheckBox = QtWidgets.QCheckBox(self.windowWidget)
        self.alacCheckBox.setText("ALAC")

        self._itunes_checkbox_init()
        self._aac_checkbox_init()
        self._alac_checkbox_init()

        self.mp3CheckBox = QtWidgets.QCheckBox(self.windowWidget)
        self.mp3CheckBox.setText("MP3")

        self.ac3CheckBox = QtWidgets.QCheckBox(self.windowWidget)
        self.ac3CheckBox.setText("AC3")

        self.flacCheckBox = QtWidgets.QCheckBox(self.windowWidget)
        self.flacCheckBox.setText("FLAC")

        self.formatsLayout = QtWidgets.QGridLayout()
        self.formatsLayout.setColumnMinimumWidth(0, 10)
        self.formatsLayout.addWidget(self.iTunesCheckBox, 0, 0, 1, 2)
        self.formatsLayout.addWidget(self.aacCheckBox, 1, 1)
        self.formatsLayout.addWidget(self.alacCheckBox, 2, 1)
        self.formatsLayout.addWidget(self.mp3CheckBox, 0, 2)
        self.formatsLayout.addWidget(self.ac3CheckBox, 1, 2)
        self.formatsLayout.addWidget(self.flacCheckBox, 2, 2)

        self.formatsGroup.setLayout(self.formatsLayout)

        self.windowLayout.addWidget(self.formatsGroup)

        self.dropFrame = DropFrame(self.windowWidget)
        self.dropFrame.setMinimumHeight(160)
        self.dropFrame.signals.accepted_drop.connect(self._analyze_drop)

        self.windowLayout.addWidget(self.dropFrame)

        self.progressBar = QtWidgets.QProgressBar(self.windowWidget)
        self.progressBar.setAlignment(QtCore.Qt.AlignCenter)

        self.windowLayout.addWidget(self.progressBar)

        self.bottomSpacer = QtWidgets.QSpacerItem(50, 10)
        self.windowLayout.addSpacerItem(self.bottomSpacer)

        self.buttonsLayout = QtWidgets.QHBoxLayout()

        self.quitButton = QtWidgets.QPushButton(self.windowWidget)
        self.quitButton.setMinimumHeight(30)
        self.quitButton.setText("Quit")

        self.stopButton = QtWidgets.QPushButton(self.windowWidget)
        self.stopButton.setMinimumHeight(30)
        self.stopButton.setText("Stop")

        self.buttonsLayout.addWidget(self.quitButton)
        self.buttonsLayout.addWidget(self.stopButton)

        self.windowLayout.addLayout(self.buttonsLayout)

    def _quit(self):
        raise SystemExit

    @QtCore.pyqtSlot()
    def _volumes_combobox_changed(self):
        self._volumes_combobox_selection = int(self.volumesComboBox.currentText())

    def _volumes_combobox_init(self):
        self.volumesComboBox.addItems([str(vol) for vol in conf.volume_choices])
        self._volumes_combobox_selection = int(self.volumesComboBox.currentText())
        self.volumesComboBox.currentTextChanged.connect(self._volumes_combobox_changed)

    @QtCore.pyqtSlot(bool)
    def _itunes_checkbox_clicked(self, checked):
        if checked:
            self.aacCheckBox.setChecked(True)
            self.alacCheckBox.setChecked(True)
        else:
            self.aacCheckBox.setChecked(False)
            self.alacCheckBox.setChecked(False)

    def _itunes_checkbox_init(self):
        self.iTunesCheckBox.clicked.connect(self._itunes_checkbox_clicked)
        self.iTunesCheckBox.click()

    @QtCore.pyqtSlot(int)
    def _aac_checkbox_changed(self, state):
        alac_checked = self.alacCheckBox.isChecked()

        if state == 0:
            self.iTunesCheckBox.setChecked(False)
            if alac_checked:
                self.alacCheckBox.setChecked(True)

        if state == 2:
            if alac_checked:
                self.iTunesCheckBox.setChecked(True)

    def _aac_checkbox_init(self):
        self.aacCheckBox.stateChanged.connect(self._aac_checkbox_changed)

    @QtCore.pyqtSlot(int)
    def _alac_checkbox_changed(self, state):
        aac_checked = self.aacCheckBox.isChecked()

        if state == 0:
            self.iTunesCheckBox.setChecked(False)
            if aac_checked:
                self.aacCheckBox.setChecked(True)

        if state == 2:
            if aac_checked:
                self.iTunesCheckBox.setChecked(True)

    def _alac_checkbox_init(self):
        self.alacCheckBox.stateChanged.connect(self._alac_checkbox_changed)

    def _analyze_drop(self):
        if conf.input.is_dir():
            self.ac3CheckBox.setDisabled(True)
        else:
            self.ac3CheckBox.setDisabled(False)

def main():
    app = QtWidgets.QApplication(sys.argv)
    widget = Dropplet()
    widget.show()
    app.exec()


if __name__ == "__main__":
    main()
