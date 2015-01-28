#!python3
# -*- coding: utf-8 -*-

import sys

from PyQt5 import QtWidgets
from PyQt5 import QtCore


class Dropplet(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("R128 Normalizer")
        self.setMinimumSize(300, 400)
        self.setMaximumSize(300, 400)

        self.verticalLayoutWidget = QtWidgets.QWidget(self)
        self.verticalLayoutWidget.setGeometry(10, 10, 280, 380)
        self.verticalLayout = QtWidgets.QVBoxLayout(self.verticalLayoutWidget)

        spacer1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacer1)

        self.volumeLabel = QtWidgets.QLabel(self.verticalLayoutWidget)
        self.volumeLabel.setText("Normalize to:")
        self.verticalLayout.addWidget(self.volumeLabel)

        self.volumeComboBox = QtWidgets.QComboBox(self.verticalLayoutWidget)
        self.volumeComboBox.setCurrentText("-16")
        self.verticalLayout.addWidget(self.volumeComboBox)

        spacer2 = QtWidgets.QSpacerItem(spacer1)
        self.verticalLayout.addItem(spacer2)

        self.formatLabel = QtWidgets.QLabel(self.verticalLayoutWidget)
        self.formatLabel.setText("Format:")
        self.verticalLayout.addWidget(self.formatLabel)

        self.formatComboBox = QtWidgets.QComboBox(self.verticalLayoutWidget)
        self.formatComboBox.setCurrentText("iTunes (AAC and ALAC)")
        self.verticalLayout.addWidget(self.formatComboBox)

        spacer3 = QtWidgets.QSpacerItem(spacer1)
        self.verticalLayout.addItem(spacer3)

        self.frame = QtWidgets.QFrame(self.verticalLayoutWidget)
        self.frame.setMinimumSize(0, 150)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.frame.setLineWidth(1)
        self.frameLabel = QtWidgets.QLabel(self.frame)
        self.frameLabel.setGeometry(10, 10, 245, 130)
        self.frameLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.frameLabel.setText("Drop Here!")
        self.verticalLayout.addWidget(self.frame)

        self.progressBar = QtWidgets.QProgressBar(self.verticalLayoutWidget)
        self.progressBar.setAlignment(QtCore.Qt.AlignCenter)
        self.verticalLayout.addWidget(self.progressBar)


def main():
    app = QtWidgets.QApplication(sys.argv)
    drop = Dropplet()
    drop.show()
    app.exec()


if __name__ == "__main__":
    main()
