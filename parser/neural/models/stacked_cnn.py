#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf

from parser.neural import linalg
from parser.configurable import Configurable
from parser.neural.models.nn import NN

#***************************************************************
class StackedCNN(NN):
  """"""
  PAD = 0
  #=============================================================
  def __init__(self, *args, **kwargs):
    """"""
    super(StackedCNN, self).__init__(*args, **kwargs)
    self._layers = self.n_layers
    self._window_size = self.window_size
    print ('### Stacked_CNN layers: {}, window size: {} ###'.format(self._layers, self._window_size))
    return

  #=============================================================
  # inputs: (batch_size, max_len, embed_size)
  # output: (batch_size, max_len, cnn_size)
  def __call__(self, inputs, output_size):
    """"""
    top_conv = inputs
    #"""
    for i in xrange(self.n_layers):
      with tf.variable_scope('StackedCNN'):
        with tf.variable_scope('CNN%d' % i):
          # top_conv: (batch_size, max_len, output_size)
          top_conv = self.CNN(top_conv, self.window_size, output_size)

    return top_conv

  #=============================================================
  def convolutional(self, inputs, window_size, output_size, keep_prob=None, n_splits=1, add_bias=True, initializer=None):
    """"""

    if isinstance(inputs, (list, tuple)):
      n_dims = len(inputs[0].get_shape().as_list())
      inputs = tf.concat(inputs, n_dims-1)
    else:
      n_dims = len(inputs.get_shape().as_list())
    #input_size = inputs.get_shape().as_list()[-1]
    batch_size, time_steps, depth = tf.unstack(tf.shape(inputs), 3)
    if self.moving_params is None:
      keep_prob = keep_prob or self.conv_keep_prob
    else:
      keep_prob = 1
      
    if keep_prob < 1:
      noise_shape = tf.stack([batch_size, 1, depth])
      inputs = tf.nn.dropout(inputs, keep_prob, noise_shape=noise_shape)
    
    conv = linalg.convolutional(inputs,
                                window_size,
                                output_size,
                                n_splits=n_splits,
                                add_bias=add_bias,
                                initializer=initializer,
                                moving_params=self.moving_params)
    
    if output_size == 1:
      if isinstance(conv, list):
        conv = [tf.squeeze(x, axis=(n_dims-1)) for x in conv]
      else:
        conv = tf.squeeze(conv, axis=(n_dims-1))
    return conv

if __name__ == "__main__":

  configurable = Configurable()
  scnn = StackedCNN.from_configurable(configurable)
  a = tf.placeholder(tf.float32, shape=[None, None, 4])
  #conv,d = scnn(a, 5)
  conv = scnn(a, 5)

  a_1 = np.reshape(np.arange(40),[2,5,4])
  print ('a_1:\n{}'.format(a_1))

  with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())
    #_conv,drop = sess.run([conv,d], feed_dict={a:a_1})
    _conv = sess.run([conv], feed_dict={a:a_1})
    print ('conv:\n{}'.format(_conv))