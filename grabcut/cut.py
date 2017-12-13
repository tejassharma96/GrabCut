"""This module contains logic for the grabcut algorithm."""
# import cv2
import numpy as np
import maxflow
# cv2.grabCut(img2, mask, rect, bgdmodel, fgdmodel, 1, cv2.GC_INIT_WITH_RECT)


'''
need 2 GMMs: foreground and background
'''


class GMM:
    """This class defines a gaussian mixture model."""

    def __init__(self, k=5):
        """Initialize with a default of k = 5."""
        self.k = k
        self.means = np.zeros((k, 3))
        self.cov = np.zeros((k, 3, 3))
        self.inv_cov = np.zeros((k, 3, 3))
        self.det_cov = np.zeros((k, 1))
        self.weights = np.zeros((k, 1))

        self.total_pixel_count = 0

        self.eigenvalues = np.zeros(k)
        self.eigenvectors = np.zeros((k, 3))
        self.pixels = [[] for _ in range(k)]

    def add_pixel(self, pixel, i):
        """Add a pixel to the GMM."""
        self.pixels[i].append(pixel.copy())
        self.total_pixel_count += 1

    def update_gmm(self):
        """Update the means and covs for the GMM."""
        for i in range(self.k):
            n = len(self.pixels[i])
            if n == 0:
                self.weights[i] = 0
            else:
                self.weights[i] = n / self.total_pixel_count
                self.means[i] = np.mean(self.pixels[i], axis=0)

                self.cov[i] = np.cov(self.pixels[i], rowvar=False, bias=True)
                # print("cov ", i, self.cov[i])
                self.det_cov[i] = np.linalg.det(self.cov[i])
                self.inv_cov[i] = np.linalg.inv(self.cov[i])

                evals, evects = np.linalg.eig(self.cov[i])
                max_ind = np.argmax(evals)
                self.eigenvalues[i] = evals[max_ind]
                self.eigenvectors[i] = evects[max_ind]

    '''
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    EITHER THIS ONE OR THE ONE BELOW WORKS
    !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    '''

    def redistribute_pixels(self):
        """Redistribute the pixels to different clusters."""
        self.update_gmm()
        for i in range(1, self.k):
            n = np.argmax(self.eigenvalues)
            e_n = self.eigenvectors[n]
            rhs = np.dot(e_n.T, self.means[n])
            lhs = np.dot(e_n.T, np.array(self.pixels[n]).T)
            # print("lhs: ", lhs)
            # print("rhs: ", rhs)
            # e_n = np.tile(e_n, (len(self.pixels[n]), 1))
            indices1 = np.where(lhs <= rhs)
            indices2 = np.where(lhs > rhs)
            # print(indices1)
            # print(indices2)
            # print(self.pixels[n])
            temp = np.asarray(self.pixels[n])
            self.pixels[i] = temp[indices1]
            self.pixels[n] = temp[indices2]
            self.update_gmm()

    # def redistribute_pixels(self):
    #     self.update_gmm()
    #     for i in range(1, self.k):
    #         n = np.argmax(self.eigenvalues)
    #         e_n = self.eigenvectors[n]
    #         rhs = np.dot(e_n.T, self.means[n])
    #         c_i = []
    #         c_n = []
    #         print("rhs: ", rhs)
    #         for pixel in self.pixels[n]:
    #             lhs = np.dot(e_n.T, pixel)
    #             print("lhs: ", lhs)
    #             if lhs <= rhs:
    #                 c_i.append(pixel)
    #             else:
    #                 c_n.append(pixel)
    #         self.pixels[i] = c_i
    #         self.pixels[n] = c_n
    #         self.update_gmm()


class GrabCut:
    """This class represents the engine for grabcut."""

    def __init__(self, img, k=5):
        """Initialize the object with an image."""
        self.img = img
        self.k = k
        self.height = img.shape[0]
        self.width = img.shape[1]
        self.trimap = np.zeros((img.shape[0], img.shape[1]))
        self.matte = np.zeros((img.shape[0], img.shape[1]))
        self.comp_index = np.zeros((img.shape[0], img.shape[1]))

    '''
    step 1
    '''
    def convert_rect_to_mask(self, rect, img):
        """Convert a rect to a trimap mask."""
        mask = np.zeros((img.shape[0], img.shape[1]))
        mask[rect[1]:rect[1] + rect[3], rect[0]:rect[0] + rect[2]] = 2
        return mask

    def convert_rect_to_matte(self, rect, img):
        """Convert a rect to a matte."""
        matte = np.zeros((img.shape[0], img.shape[1]))
        matte[rect[1]:rect[1] + rect[3], rect[0]:rect[0] + rect[2]] = 1
        return matte

    def set_bgd_fgd(self):
        """Set the background and foreground pixel sets."""
        self.bgd = np.where(self.trimap == 0)
        self.fgd = np.where(np.logical_or(self.trimap == 1, self.trimap == 2))
        self.bgd_pixels = self.img[self.bgd]
        self.fgd_pixels = self.img[self.fgd]

    def prob_pixel_in_gmm(self, pixel, model):
        """Calculate the probability a pixel is in the specified GMM."""
        sum = 0
        for i in (1, 6):
            sum += model.weights[i] / np.sqrt(model.det_cov[i])
            * np.exp(0.5 * np.dot((pixel - model.means[i]).T * (np.dot(model.inv_cov, pixel - model.mean[i]))))

        return -np.log(sum)

    def get_beta(self):
        """Get the beta value based on the paper."""
        left_diffs = self.img[:, 1:] - self.img[:, :-1]
        upleft_diffs = self.img[1:, 1:] - self.img[:-1, :-1]
        up_diffs = self.img[1:, :] - self.img[:-1, :]
        upright_diffs = self.img[1:, :-1] - self.img[:-1, 1:]
        sum_squared = (left_diffs * left_diffs).sum() + (upleft_diffs * upleft_diffs).sum() + \
                      (up_diffs * up_diffs).sum() + (upright_diffs * upright_diffs).sum()
        beta = sum_squared / (4 * self.img.shape[0] * self.img.shape[1] - 3 * (self.img.shape[0] + self.img.shape[1]) + 2)
        return 1 / (2 * beta)

    def build_n_link(self, nodeids):
        """Build the neighbour links."""
        diag_left = np.zeros((self.img.shape[0], self.img.shape[1]))
        diag_right = np.zeros((self.img.shape[0], self.img.shape[1]))
        up = np.zeros((self.img.shape[0], self.img.shape[1]))
        left = np.zeros((self.img.shape[0], self.img.shape[1]))

        beta = self.get_beta()

        for y in range(self.height):
            for x in range(self.width):
                z_m = self.img[y][x]
                if y > 0 and x > 0:
                    diag_left[y][x] = 50 / np.sqrt(2) * np.exp(-beta * (z_m - self.img[y - 1][x - 1])**2)
                if y > 0 and x < self.img.shape[1] - 1:
                    diag_right[y][x] = 50 / np.sqrt(2) * np.exp(-beta * (z_m - self.img[y - 1][x + 1])**2)
                if x > 0:
                    left[y][x] = 50 * np.exp(-beta * (z_m - self.img[y][x - 1])**2)
                if y > 0:
                    up[y][x] = 50 * np.exp(-beta * (z_m - self.img[y - 1][x])**2)

        self.max_weight = max(max(diag_left), max(
            diag_right), max(left), max(up))

        diag_left_struct = np.array([[1, 0, 0], [0, 0, 0], [0, 0, 0]])
        diag_right_struct = np.array([[0, 0, 1], [0, 0, 0], [0, 0, 0]])
        up_struct = np.array([[0, 1, 0], [0, 0, 0], [0, 0, 0]])
        left_struct = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 0]])
        self.graph.add_grid_edges(nodeids, weights=diag_left, structure=diag_left_struct,
                                  symmetric=True)
        self.graph.add_grid_edges(nodeids, weights=diag_right, structure=diag_right_struct,
                                  symmetric=True)
        self.graph.add_grid_edges(nodeids, weights=left, structure=left_struct,
                                  symmetric=True)
        self.graph.add_grid_edges(nodeids, weights=up, structure=up_struct,
                                  symmetric=True)

    def build_t_link(self, nodeids):
        """Build the target links."""
        for y in range(self.height):
            for x in range(self.width):
                if self.trimap[y][x] == 0:
                    self.graph.add_tedge(nodeids[y][x], 0, self.max_weight)
                elif self.trimap[y][x] == 1:
                    self.graph.add_tedge(nodeids[y][x], self.max_weight, 0)
                else:
                    d_f = self.prob_pixel_in_gmm(self.img[y][x], self.foreground_gmm)
                    d_b = self.prob_pixel_in_gmm(self.img[y][x], self.background_gmm)
                    self.graph.add_tedge(nodeids[y][x], d_f, d_b)

    '''
    inputs:
        img: np.array
        mask: np.array
        rect: (start.x, start.y, end.x, end.y)
        background: np.array
        foreground: np.array
        iteration: int
        use_mask: bool
    outputs:

    '''
    def grab_cut(self, img, mask, rect, background, foreground, iteration, use_mask):
        """Perform an iteration of grabcut."""
        if not use_mask:
            self.trimap = self.convert_rect_to_mask(rect, img)
            self.matte = self.convert_rect_to_matte(rect, img)

        self.set_bgd_fgd()
        foreground_gmm = GMM()
        background_gmm = GMM()

        for pixel in self.fgd_pixels:
            foreground_gmm.add_pixel(pixel, 0)

        for pixel in self.bgd_pixels:
            background_gmm.add_pixel(pixel, 0)

        foreground_gmm.redistribute_pixels()
        background_gmm.redistribute_pixels()

        foreground_gmm.update_gmm()
        background_gmm.update_gmm()

        # build the graph
        self.graph = maxflow.graph[float]()
        nodeids = self.graph.add_grid_nodes(
            (self.img.shape[0], self.img.shape[1]))
        self.graph.maxflow()

        sgm = self.graph.get_grid_segments(nodeids)
        sgm = np.bitwise_and(sgm, self.matte)
