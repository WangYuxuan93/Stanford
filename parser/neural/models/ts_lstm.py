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
class TS_LSTM(NN):
  """"""
  PAD = 0
  #=============================================================
  def __init__(self, *args, **kwargs):
    """"""
    super(TS_LSTM, self).__init__(*args, **kwargs)
    self._window_size = self.window_size
    self._time_stride = self.time_stride
    self._parallel_iterations = 5
    print ('### TS_LSTM window size:',self._window_size, ' time stride:',self._time_stride, " ###")
    try:
      assert(self._window_size >= self._time_stride)
    except AssertionError:
      raise ValueError("### Window size (%d) should not be less than time stride (%d)! ###" 
                        % (self._window_size, self._time_stride))
    return

  #=============================================================
  # inputs: (batch_size, max_len, embed_size)
  # output: (batch_size, max_len, recur_size) recur_size = output_size * 2 if use birnn
  def __call__(self, inputs, output_size, placeholder, moving_params=None):
    """"""
    self.moving_params = moving_params
    self._batch_size = tf.shape(placeholder)[0]
    slided, s_seq_lens, remain, r_seq_lens = self.split_to_slide(inputs, placeholder)
    
    #"""
    for i in xrange(self.n_layers):
      with tf.variable_scope('TS_LSTM'):
        with tf.variable_scope('RNN%d' % i):
          slided, _ = self.RNN(slided, output_size, s_seq_lens)
        with tf.variable_scope('RNN%d' % i, reuse = True):
          remain, _ = self.RNN(remain, output_size, r_seq_lens)
    #"""
    output = self.slide_to_output(slided, remain, inputs, output_size)
    #return slided, s_seq_lens, remain, r_seq_lens, output
    return output

  #=============================================================
  def set(self, window_size, time_stride):
    self._window_size = window_size
    self._time_stride = time_stride
    print ('### TS_LSTM window size:',self._window_size, ' time stride:',self._time_stride, " ###")
    return

  #=============================================================
  def slide_to_output(self, slided, remain, inputs, recur_size):
    batch_size = tf.shape(inputs)[0]
    seq_len = tf.shape(inputs)[1]
    #recur_size = tf.shape(inputs)[2]
    #recur_size = tf.shape(slided)[2]
    #print ("rnn_func:",self.rnn_func.__name__)
    recur_size = 2 * recur_size if self.rnn_func.__name__ == "birnn" else recur_size
    remain_start = seq_len - tf.shape(remain)[1]

    slided = tf.expand_dims(slided, 2)
    slided = tf.cond(tf.greater_equal(seq_len, self._window_size),
                  lambda: tf.reshape(slided, [-1, batch_size, self._window_size, recur_size]),
                  lambda: tf.reshape(slided, [-1, batch_size, seq_len, recur_size]))
    n_window = tf.shape(slided)[0]
    offset = tf.constant(1)
    output = slided[0,:,0:1,:]
    # n * step <= offset < n * step + wind
    # (offset - wind) / step < n <= offset / step
    #"""
    def collect(n, offset, col):
      pos = tf.to_int32(offset - n * self._time_stride)
      col = tf.add(col, slided[n,:,pos:pos+1,:])
      return (n + 1, offset, col)

    def slide(offset, output):
      n = tf.cond(tf.less(offset, self._window_size), lambda: 0, 
            lambda: tf.to_int32((offset - self._window_size) / self._time_stride) + 1)
      #n = tf.to_int32(tf.floor((offset - self._window_size) / self._time_stride)) + 1
      #n = tf.maximum(n, 0)
      pos = tf.to_int32(offset - n * self._time_stride)
      col = slided[n,:,pos:pos+1,:]
      n = tf.add(n, 1)
      n, offset, col = tf.while_loop(
        cond = lambda n, offset, _2: tf.logical_and(tf.logical_and(tf.less_equal(n * self._time_stride, offset), 
                                      tf.greater(n * self._time_stride + self._window_size, offset)),
                                      tf.less(n, n_window)),
        body = collect,
        loop_vars = (n, offset, col),
        parallel_iterations = self._parallel_iterations,
        swap_memory = True)
      #outputs.append(col)
      output = tf.concat([output, col], 1)
      return (offset + 1, output)

    offset, output = tf.while_loop(
      #cond = lambda offset, _1: offset + self._window_size <= seq_len,
      cond = lambda offset, _1: offset < remain_start,
      body = slide,
      loop_vars = (offset, output),
      shape_invariants = (offset.get_shape(), tf.TensorShape([None, None, recur_size])),
      parallel_iterations = self._parallel_iterations,
      swap_memory = True)

    #"""
    def add_remain(offset, output):
      n = tf.cond(tf.less(offset, self._window_size), lambda: 0, 
            lambda: tf.to_int32((offset - self._window_size) / self._time_stride) + 1)
      #n = tf.to_int32(tf.floor((offset - self._window_size) / self._time_stride)) + 1
      #n = tf.maximum(n, 0)
      pos = tf.to_int32(offset - n * self._time_stride)
      col = remain[:,(offset-remain_start):(offset-remain_start+1),:]

      n, offset, col = tf.while_loop(
        cond = lambda n, offset, _2: tf.logical_and(tf.logical_and(tf.less_equal(n * self._time_stride, offset), 
                                      tf.greater(n * self._time_stride + self._window_size, offset)),
                                      tf.less(n, n_window)),
        body = collect,
        loop_vars = (n, offset, col),
        parallel_iterations = self._parallel_iterations,
        swap_memory = True)

      output = tf.concat([output, col], 1)
      return (offset + 1, output)

    offset, output = tf.while_loop(
      cond = lambda offset, _1 : offset < seq_len,
      body = add_remain,
      loop_vars = (offset, output),
      shape_invariants = (offset.get_shape(), tf.TensorShape([None, None, recur_size])),
      parallel_iterations = self._parallel_iterations,
      swap_memory = True)
    #"""
    
    return output

  #=============================================================
  def split_to_slide(self, inputs, placeholder):
    seq_len = tf.shape(inputs)[1]
    offset = tf.cond(tf.greater_equal(seq_len,self._window_size), lambda: tf.constant(self._time_stride), lambda: seq_len)
    slided = tf.cond(tf.greater_equal(seq_len,self._window_size), lambda: inputs[:, :self._window_size, :], lambda: inputs[:, :, :])
    #slided = tf.slice(inputs, [0, 0, 0], [-1, offset, -1])
    s_seq_lens = tf.cond(tf.greater_equal(seq_len,self._window_size),
      lambda: tf.reduce_sum(tf.to_int32(tf.greater(placeholder[:,:self._window_size], self.PAD)), axis=1),
      lambda: tf.reduce_sum(tf.to_int32(tf.greater(placeholder[:,:], self.PAD)), axis=1))

    def slide(offset, slided, s_seq_lens):
      #slided = tf.concat([slided, tf.slice(inputs, [0, offset, 0], [-1, self._window_size, -1])], 0)
      slided = tf.concat([slided, inputs[:, offset : offset+self._window_size, :]], 0)
      lens = tf.reduce_sum(tf.to_int32(tf.greater(placeholder[:,offset : offset+self._window_size], self.PAD)), axis=1)
      s_seq_lens = tf.concat([s_seq_lens, lens], 0)
      return (offset + self._time_stride, slided, s_seq_lens)
    
    offset, slided, s_seq_lens = tf.while_loop(
      cond = lambda offset, _1, _2: offset + self._window_size <= seq_len,
      body = slide,
      loop_vars = (offset, slided, s_seq_lens),
      parallel_iterations = self._parallel_iterations,
      swap_memory = True)
    
    #remain = tf.cond(tf.less(offset,seq_len),lambda: inputs[:, offset:, :],lambda: inputs[:,:,:])
    remain = tf.cond(tf.less(offset, seq_len),lambda: inputs[:, offset:, :], lambda: inputs[:, seq_len-1:,:])
    #r_seq_lens = tf.cond(tf.less(offset, seq_len), 
                          #lambda: tf.reduce_sum(tf.to_int32(tf.greater(placeholder[:,offset:], self.PAD)), axis=1),
                          #lambda: tf.reduce_sum(tf.to_int32(tf.greater(placeholder[:,seq_len:], self.PAD)), axis=1))
    r_seq_lens = tf.reduce_sum(tf.to_int32(tf.greater(placeholder[:,offset:], self.PAD)), axis=1)

    return (slided, s_seq_lens, remain, r_seq_lens)

  #=============================================================
  def RNN(self, inputs, output_size, sequence_lengths):
    """"""
    
    input_size = inputs.get_shape().as_list()[-1]
    cell = self.recur_cell.from_configurable(self, output_size, input_size=input_size, moving_params=self.moving_params)
    
    if self.moving_params is None:
      ff_keep_prob = self.ff_keep_prob
      recur_keep_prob = self.recur_keep_prob
    else:
      ff_keep_prob = 1
      recur_keep_prob = 1
    #print ("nn.py(RNN):cell:",cell,"self.rnn_func:",self.rnn_func)
    #exit() 
    top_recur, end_state = self.rnn_func(cell, inputs, sequence_lengths,
                                 ff_keep_prob=ff_keep_prob,
                                 recur_keep_prob=recur_keep_prob)
    return top_recur, end_state

  #=============================================================
  #@property
  #def window_size(self):
  #  return self._window_size
  #@property
  #def time_stride(self):
  #  return self._time_stride

if __name__ == "__main__":

  configurable = Configurable()
  ts = TS_LSTM.from_configurable(configurable)
  a = tf.placeholder(tf.float32, shape=[None, None, 4])
  holder = tf.placeholder(tf.int32, shape = [None, None])
  s, sl, r, rl, o = ts(a, 3, holder)

  a_1 = np.reshape(np.arange(40),[2,5,4])
  h_1 = np.array([[1,2,5,4,5],[2,3,4,0,0]])
  a_2 = np.reshape(np.arange(56),[2,7,4])
  h_2 = np.array([[1,2,5,4,1,6,0],[2,3,4,0,0,0,0]])
  print ('a_1:\n',a_1,'\na_2:\n',a_2)
  with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())
    _s, _sl, _r, _rl, _o = sess.run([s, sl, r, rl,o], feed_dict={a:a_1,holder:h_1})
    print('\ns:\n',_s,'\nsl:\n',_sl,'\nr:\n', _r,'\nrl:\n',_rl,'\noutput:\n',_o)
    _s, _sl, _r, _rl, _o = sess.run([s, sl, r, rl,o], feed_dict={a:a_2,holder:h_2})
    print('\ns:\n',_s,'\nsl:\n',_sl,'\nr:\n', _r,'\nrl:\n',_rl,'\noutput:\n',_o)