#!/usr/bin/env python
#
# Copyright (C) 2014  Antoine Drouin
#
# This file is part of paparazzi.
#
# paparazzi is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# paparazzi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with paparazzi; see the file COPYING.  If not, write to
# the Free Software Foundation, 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.
#
"""
This is a graphical user interface for playing with reference attitude
"""
# https://gist.github.com/zed/b966b5a04f2dfc16c98e
# https://gist.github.com/nzjrs/51686
# http://jakevdp.github.io/blog/2012/10/07/xkcd-style-plots-in-matplotlib/
# http://chimera.labs.oreilly.com/books/1230000000393/ch12.html#_problem_208  <- threads

# TODO:
#   -cancel workers
#
#
#

from gi.repository import Gtk, GObject
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
import matplotlib.font_manager as fm

import math, threading, numpy as np, scipy.signal, pdb, copy, logging

import pat.utils as pu
import pat.algebra as pa
import control as ctl
import gui


class Reference(gui.Worker):
    t_default, t_sat1, t_sat2, t_nb = range(0, 4)
    t_names = ["python default", "python saturated naive", "python saturated nested"]
    impls = [ctl.att_ref, ctl.att_ref_sat_naive]

    def __init__(self, sp, _type=t_default, _omega=6., _xi=0.8, _max_vel=pu.rad_of_deg(100),
                 _max_accel=pu.rad_of_deg(500)):
        gui.Worker.__init__(self)
        self.sp = sp
        # self.update_sp(sp, _type, _omega, _xi, _max_vel, _max_accel)

    def update_type(self, _type):
        print 'update_type', _type
        self.impl = _type()
        self.recompute()

    def update_param(self, p, v):
        print 'update_param', p, v
        self.impl.set_param(p, v)
        self.recompute()

    def update_sp(self, sp, _type=None, _omega=None, _xi=None, _max_vel=None, _max_accel=None):
        self.euler = np.zeros((len(sp.time), pa.e_size))
        self.quat = np.zeros((len(sp.time), pa.q_size))
        self.vel = np.zeros((len(sp.time), pa.r_size))
        self.accel = np.zeros((len(sp.time), pa.r_size))
        # self.update(sp, _type, _omega, _xi, _max_vel, _max_accel)

    def update(self, sp, _type=None, _omega=None, _xi=None, _max_vel=None, _max_accel=None):
        if _omega <> None: self.omega = _omega
        if _xi <> None: self.xi = _xi
        if _max_vel <> None: self.max_vel = _max_vel
        if _max_accel <> None: self.max_accel = _max_accel
        if _type <> None:
            self.type = _type
            self.impl = Reference.impls[_type](omega=self.omega * np.ones(3), xi=self.xi * np.ones(3))
            # self.impl.set_params(self.omega*np.ones(3), self.xi*np.ones(3), self.max_vel*np.ones(3), self.max_accel*np.ones(3))
            # self.up_to_date = False
            # pdb.set_trace()
            # foo = copy.deepcopy(sp,)
            # self.work(None, (sp,))

    def recompute(self):
        self.up_to_date = False
        self.start((self.sp,))

    def _work_init(self, sp):
        print '_work_init ', self, self.impl, sp, sp.dt
        self.euler = np.zeros((len(sp.time), pa.e_size))
        self.quat = np.zeros((len(sp.time), pa.q_size))
        self.vel = np.zeros((len(sp.time), pa.r_size))
        self.accel = np.zeros((len(sp.time), pa.r_size))
        euler0 = [0.3, 0.1, 0.2]
        self.impl.set_euler(np.array(euler0))
        self.quat[0], self.euler[0], self.vel[0], self.accel[
            0] = self.impl.quat, self.impl.euler, self.impl.vel, self.impl.accel
        self.n_iter_per_step = float(len(sp.time)) / self.n_step

    def _work_step(self, i, sp):
        start, stop = int(i * self.n_iter_per_step), int((i + 1) * self.n_iter_per_step)
        # print '_work_step', start, stop
        for j in range(start, stop):
            self.quat[j], self.vel[j], self.accel[j] = self.impl.update_quat(sp.quat[j], sp.dt)
            self.euler[j] = pa.euler_of_quat(self.quat[j])

    def _work_done(self, sp):
        print '_work_done'


class Setpoint():
    t_static, t_step_phi, t_step_theta, t_step_psi, t_step_random, t_nb = range(0, 6)
    t_names = ["constant", "step phi", "step theta", "step psi", "step_random"]

    def __init__(self, type=t_static, duration=10., step_duration=5., step_ampl=pu.rad_of_deg(10.)):
        self.dt = 1. / 512
        self.update(type, duration, step_duration, step_ampl)

    def update(self, type, duration, step_duration, step_ampl):
        self.type = type
        self.duration, self.step_duration, self.step_ampl = duration, step_duration, step_ampl
        self.time = np.arange(0., self.duration, self.dt)
        self.euler = np.zeros((len(self.time), pa.e_size))
        try:
            i = [Setpoint.t_step_phi, Setpoint.t_step_theta, Setpoint.t_step_psi].index(self.type)
            self.euler[:, i] = step_ampl / 2 * scipy.signal.square(math.pi / step_duration * self.time)
        except:
            pass

        self.quat = np.zeros((len(self.time), pa.q_size))
        for i in range(0, len(self.time)):
            self.quat[i] = pa.quat_of_euler(self.euler[i])


class GUI():
    def __init__(self, sp, refs):
        self.b = Gtk.Builder()
        self.b.add_from_file("att_ref_gui.xml")
        w = self.b.get_object("window")
        w.connect("delete-event", Gtk.main_quit)
        mb = self.b.get_object("main_vbox")
        self.plot = Plot(sp, refs)
        mb.pack_start(self.plot, True, True, 0)
        mb = self.b.get_object("main_hbox")
        ref_classes = [ctl.att_ref, ctl.att_ref_sat_naive, ctl.att_ref_sat_nested, ctl.att_ref_sat_nested2]
        self.refs = [gui.AttRefParamView('<b>Ref {}</b>'.format(i), ref_classes=ref_classes) for i in range(1, 3)]
        for r in self.refs:
            mb.pack_start(r, True, True, 0)
        w.show_all()


class Plot(Gtk.Frame):
    def __init__(self, sp, refs):
        Gtk.Frame.__init__(self)
        self.f = Figure()
        self.canvas = FigureCanvas(self.f)
        self.add(self.canvas)
        self.set_size_request(1024, 600)
        self.f.subplots_adjust(left=0.07, right=0.98, bottom=0.05, top=0.95,
                               hspace=0.2, wspace=0.2)
        # self.buffer = self.canvas.get_snapshot()

    def decorate(self, axis, title=None, ylab=None, legend=None):
        # font_prop = fm.FontProperties(fname='Humor-Sans-1.0.ttf', size=14)
        if title is not None:
            axis.set_title(title)  # , fontproperties=font_prop)
        if ylab is not None:
            axis.yaxis.set_label_text(ylab)  # , fontproperties=font_prop)
        if legend is not None:
            axis.legend(legend)  # , prop=font_prop)
        axis.xaxis.grid(color='k', linestyle='-', linewidth=0.2)
        axis.yaxis.grid(color='k', linestyle='-', linewidth=0.2)

    def update(self, sp, refs):
        title = [r'$\phi$', r'$\theta$', r'$\psi$']
        legend = ['Ref1', 'Ref2', 'Setpoint']
        for i in range(0, 3):
            axis = self.f.add_subplot(331 + i)
            axis.clear()
            for ref in refs: axis.plot(sp.time, pu.deg_of_rad(ref.euler[:, i]))
            axis.plot(sp.time, pu.deg_of_rad(sp.euler[:, i]))
            self.decorate(axis, title[i], *(('deg', legend) if i == 0 else (None, None)))

        title = [r'$p$', r'$q$', r'$r$']
        for i in range(0, 3):
            axis = self.f.add_subplot(334 + i)
            axis.clear()
            for ref in refs:
                axis.plot(sp.time, pu.deg_of_rad(ref.vel[:, i]))
            self.decorate(axis, title[i], 'deg/s' if i == 0 else None)

        title = [r'$\dot{p}$', r'$\dot{q}$', r'$\dot{r}$']
        for i in range(0, 3):
            axis = self.f.add_subplot(337 + i)
            axis.clear()
            for ref in refs:
                axis.plot(sp.time, pu.deg_of_rad(ref.accel[:, i]))
            self.decorate(axis, title[i], 'deg/s2' if i == 0 else None)

        self.canvas.draw()


class Application():
    def __init__(self):
        self.sp = Setpoint()
        self.refs = [Reference(self.sp), Reference(self.sp)]
        for nref, r in enumerate(self.refs):
            r.connect("progress", self.on_ref_update_progress, nref + 1)
            r.connect("completed", self.on_ref_update_completed, nref + 1)
        self.gui = GUI(self.sp, self.refs)
        self.register_gui()
        self._on_ref_changed(None, self.refs[0], self.gui.refs[0])
        self._on_ref_changed(None, self.refs[1], self.gui.refs[1])

    def on_ref_update_progress(self, ref, v, nref):
        # print 'progress', ref, v
        self.gui.b.get_object("progressbar_ref_{}".format(nref)).set_fraction(v)

    def on_ref_update_completed(self, ref, nref):
        print 'on_ref_update_completed', ref, nref
        self.gui.b.get_object("progressbar_ref_{}".format(nref)).set_fraction(1.)
        for r in self.refs:
            if r.running:
                print 'not repainting'
                return
        print 'repainting'
        self.gui.plot.update(self.sp, self.refs)

    def register_gui(self):
        self.register_setpoint()
        for i in range(0, 2):
            self.gui.refs[i].connect(self._on_ref_changed, self._on_ref_param_changed, self.refs[i], self.gui.refs[i])

    def register_setpoint(self):
        b = self.gui.b
        c_sp_type = b.get_object("combo_sp_type")
        for n in Setpoint.t_names: c_sp_type.append_text(n)
        c_sp_type.set_active(self.sp.type)
        c_sp_type.connect("changed", self.on_sp_changed)

        names = ["spin_sp_duration", "spin_sp_step_duration", "spin_sp_step_amplitude"]
        widgets = [b.get_object(name) for name in names]
        adjs = [Gtk.Adjustment(self.sp.duration, 1, 100, 1, 10, 0),
                Gtk.Adjustment(self.sp.step_duration, 0.1, 10., 0.1, 1., 0),
                Gtk.Adjustment(pu.deg_of_rad(self.sp.step_ampl), 0.1, 180., 1, 10., 0)]
        for i, w in enumerate(widgets):
            w.set_adjustment(adjs[i])
            w.update()
            w.connect("value-changed", self.on_sp_changed)

    def on_sp_changed(self, widget):
        b = self.view.b
        _type = b.get_object("combo_sp_type").get_active()
        names = ["spin_sp_duration", "spin_sp_step_duration", "spin_sp_step_amplitude"]
        _duration, _step_duration, _step_amplitude = [b.get_object(name).get_value() for name in names]
        print widget, _type, _duration, _step_duration, _step_amplitude
        _step_amplitude = pu.rad_of_deg(_step_amplitude)
        self.sp.update(_type, _duration, _step_duration, _step_amplitude)
        for r in self.refs: r.update_sp(self.sp)

    def _on_ref_changed(self, widget, ref, view):
        print '_on_ref_changed', widget, ref, view
        ref.update_type(view.get_selected_ref_class())
        view.update(ref.impl)

    def _on_ref_param_changed(self, widget, p, ref, view):
        print '_on_ref_param_changed', widget, ref, view
        val = view.spin_cfg[p]['d2r'](widget.get_value())
        ref.update_param(p, val)

    def run(self):
        Gtk.main()


if __name__ == "__main__":
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    Application().run()
