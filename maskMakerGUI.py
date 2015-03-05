#!/usr/bin/env python
"""
 Load a cspad image from the commandline arguement
 Show pixel location from the mouse position
 Show pixel value from the mouse position
 Clicking should add to the mask
 Some sort of ROI?
"""

import argparse
import h5py
from PyQt4 import QtGui
import pyqtgraph as pg
import numpy as np
import scipy

cspad_psana_shape = (4, 8, 185, 388)
cspad_geom_shape  = (1480, 1552)

def parse_cmdline_args():
    parser = argparse.ArgumentParser(description='CsPadMaskMaker - mask making, but with a mouse!')
    parser.add_argument('cspad_fnam', type=str, help="filename for the hdf5 cspad image file.")
    parser.add_argument('h5path', type=str, help="hdf5 path for the 2D cspad data.")
    return parser.parse_args()
    
def unbonded_pixels():
    def ijkl_to_ss_fs(cspad_ijkl):
        """ 
        0: 388        388: 2 * 388  2*388: 3*388  3*388: 4*388
        (0, 0, :, :)  (1, 0, :, :)  (2, 0, :, :)  (3, 0, :, :)
        (0, 1, :, :)  (1, 1, :, :)  (2, 1, :, :)  (3, 1, :, :)
        (0, 2, :, :)  (1, 2, :, :)  (2, 2, :, :)  (3, 2, :, :)
        ...           ...           ...           ...
        (0, 7, :, :)  (1, 7, :, :)  (2, 7, :, :)  (3, 7, :, :)
        """
        if cspad_ijkl.shape != cspad_psana_shape :
            raise ValueError('cspad input is not the required shape:' + str(cspad_psana_shape) )

        cspad_ij = np.zeros(cspad_geom_shape, dtype=cspad_ijkl.dtype)
        for i in range(4):
            cspad_ij[:, i * cspad_psana_shape[3]: (i+1) * cspad_psana_shape[3]] = cspad_ijkl[i].reshape((cspad_psana_shape[1] * cspad_psana_shape[2], cspad_psana_shape[3]))

        return cspad_ij

    mask = np.ones(cspad_psana_shape)

    for q in range(cspad_psana_shape[0]):
        for p in range(cspad_psana_shape[1]):
            for a in range(2):
                for i in range(19):
                    mask[q, p, i * 10, i * 10] = 0
                    mask[q, p, i * 10, i * 10 + cspad_psana_shape[-1]/2] = 0

    mask_slab = ijkl_to_ss_fs(mask)

    import scipy.signal
    mask_pad = scipy.signal.convolve(1 - mask_slab.astype(np.float), np.ones((3, 3), dtype=np.float), mode = 'same') < 1
    return mask_pad

def asic_edges():
    mask_edges = np.ones(cspad_geom_shape)
    mask_edges[:: 185, :] = 0
    mask_edges[-1, :] = 0
    mask_edges[:, :: 194] = 0
    mask_edges[:, -1] = 0

    mask_edges_pad = scipy.signal.convolve(1 - mask_edges.astype(np.float), np.ones((8, 8), dtype=np.float), mode = 'same') < 1
    return mask_edges_pad


class Application:
    def __init__(self, cspad):
        self.cspad = cspad
        self.mask  = np.ones_like(cspad, dtype=np.bool)

        self.mask_edges = False
        self.mask_unbonded = False

        self.unbonded_pixels = unbonded_pixels()
        self.asic_edges      = asic_edges()

        self.initUI()

    def updateDisplayRGB(self):
        """
        Make an RGB image (N, M, 3) (pyqt will interprate this as RGB automatically)
        with masked pixels shown in blue at the maximum value of the cspad. 
        This ensures that the masked pixels are shown at full brightness.
        """
        trans      = np.fliplr(self.cspad.T)
        trans_mask = np.fliplr(self.mask.T)
        cspad_max  = self.cspad.max()

        # convert to RGB
        # Set masked pixels to B
        display_data = np.zeros((trans.shape[0], trans.shape[1], 3), dtype = self.cspad.dtype)
        display_data[:, :, 0] = trans * trans_mask
        display_data[:, :, 1] = trans * trans_mask
        display_data[:, :, 2] = trans + (cspad_max - trans) * ~trans_mask
        
        self.plot.setImage(display_data, autoRange = False, autoLevels = False, autoHistogramRange = False)

    def generate_mask(self):
        self.mask.fill(1)

        if self.mask_unbonded :
            self.mask *= self.unbonded_pixels

        if self.mask_edges :
            self.mask *= self.asic_edges

    def update_mask_unbonded(self, state):
        if state > 0 :
            print 'adding unbonded pixels to the mask'
            self.mask_unbonded = True
        else :
            print 'removing unbonded pixels from the mask'
            self.mask_unbonded = False
        
        self.generate_mask()
        self.updateDisplayRGB()

    def update_mask_edges(self, state):
        if state > 0 :
            print 'adding asic edges to the mask'
            self.mask_edges = True
        else :
            print 'removing asic edges from the mask'
            self.mask_edges = False
        
        self.generate_mask()
        self.updateDisplayRGB()
    
    def initUI(self):
        ## Always start by initializing Qt (only once per application)
        app = QtGui.QApplication([])

        ## Define a top-level widget to hold everything
        w = QtGui.QWidget()

        self.plot = pg.ImageView()

        ## Create some widgets to be placed inside
        unbonded_checkbox = QtGui.QCheckBox('unbonded pixels')
        unbonded_checkbox.stateChanged.connect( self.update_mask_unbonded )

        edges_checkbox = QtGui.QCheckBox('asic edges')
        edges_checkbox.stateChanged.connect( self.update_mask_edges )

        # mouse hover ij value label
        ij_label = QtGui.QLabel()
        disp = 'ss fs {0:5} {1:5}   value {2:6}'.format('-', '-', '-')
        ij_label.setText(disp)
        self.plot.scene.sigMouseMoved.connect( lambda x: self.mouseMoved(ij_label, self.cspad, self.plot, x) )

        ## Create a grid layout to manage the widgets size and position
        layout = QtGui.QGridLayout()
        w.setLayout(layout)

        ## Add widgets to the layout in their proper positions
        layout.addWidget(ij_label, 0, 0)                # upper-left
        layout.addWidget(unbonded_checkbox, 1, 0)       # middle-left
        layout.addWidget(edges_checkbox, 2, 0)          # bottom-left
        layout.addWidget(self.plot, 0, 1, 3, 1)         # plot goes on right side, spanning 3 rows
        layout.setColumnStretch(1, 1)
        layout.setColumnMinimumWidth(0, 200)
        
        # display the image
        self.plot.setImage(np.fliplr(self.cspad.T))

        ## Display the widget as a new window
        w.show()

        ## Start the Qt event loop
        app.exec_()
    
    def mouseMoved(self, ij_label, cspad, plot, pos):
        img = plot.getImageItem()
        ij = [cspad.shape[0] - 1 - int(img.mapFromScene(pos).y()), int(img.mapFromScene(pos).x())] # ss, fs
        if (0 <= ij[0] < cspad.shape[0]) and (0 <= ij[1] < cspad.shape[1]):
            ij_label.setText('ss fs value: ' + str(ij[0]).rjust(5) + str(ij[1]).rjust(5) + str(cspad[ij[0], ij[1]]).rjust(8) )

if __name__ == '__main__':
    args = parse_cmdline_args()

    # load the image
    cspad = h5py.File(args.cspad_fnam, 'r')[args.h5path].value
    
    # start the gui
    Application(cspad)
