"""
PyQt5 Canvas for BSL's StreamViewer.
"""
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QPointF, QTimer, QRectF

from ._backend import _Backend, _Event, _Annotation
from ...utils._docs import fill_doc, copy_doc

# pg.setConfigOptions(antialias=True)


@fill_doc
class _BackendPyQtGraph(_Backend):
    """
    PyQtGraph backend for BSL's StreamViewer.

    Parameters
    ----------
    %(viewer_scope)s
    %(viewer_backend_geometry)s
    %(viewer_backend_xRange)s
    %(viewer_backend_yRange)s
    """

    # ---------------------------- Init ---------------------------
    def __init__(self, scope, geometry, xRange, yRange):
        super().__init__(scope, geometry, xRange, yRange)

        # Variables
        self._available_colors = np.random.uniform(
            size=(self._scope.nb_channels, 3), low=128, high=230)
        self._init_variables()

        # Canvas
        self._win = pg.GraphicsLayoutWidget(
            size=geometry[2:],
            title=f'Stream Viewer: {self._scope.stream_name}')
        self._win.show()
        self._plot_handler = self._win.addPlot()  # pyqtgraph.PlotItem
        subsampling_ratio = self._scope.sample_rate / 64
        self._plot_handler.setDownsampling(ds=subsampling_ratio,
                                           auto=None, mode='mean')
        self._plot_handler.setMouseEnabled(x=False, y=False)
        self._plot_handler.setMenuEnabled(False)
        self._init_canvas()

        # Plots
        self._plot_handler.clear()
        self._plots = dict()
        # Add PlotDataItem
        for k, idx in enumerate(self._scope.selected_channels):
            self._plots[idx] = self._plot_handler.plot(
                x=self._x_arr,
                y=self._scope.data_buffer[
                    idx, -self._duration_plot_samples:]+self._offset[k],
                pen=pg.mkColor(self._available_colors[idx, :]))

        # Connect
        self._connect_signals_to_slots()

        # Annotations
        self._first_click_position = None
        self._AnnotationThread.start()

        # Timer
        self._timer = QTimer(self._win)
        self._timer.timeout.connect(self._update_loop)

    @copy_doc(_Backend._init_variables)
    def _init_variables(self):
        super()._init_variables()

        # yRange
        self._offset = np.arange(
            0, -len(self._scope.selected_channels)*self._yRange,
            -self._yRange)

    def _init_canvas(self):
        """
        Initialize the drawing canvas.
        """
        # Ranges
        self._plot_handler.disableAutoRange()
        yRange = [
            1.5*self._yRange,
            -self._yRange*(len(self._scope.selected_channels)+1)]
        self._plot_handler.setRange(
            xRange=[0, self._xRange],
            yRange=yRange)
        self._plot_handler.showGrid(y=True)

        # Y-axis
        yticks = [(-k*self._yRange, self._scope.channels_labels[idx])
                  for k, idx in enumerate(self._scope.selected_channels)]
        ticks = [yticks, []]  # [major, minor]
        self._plot_handler.getAxis('left').setTicks(ticks)
        self._plot_handler.setLabel(
            axis='left', text=f'Scale (uV): {self._yRange}')

        # X-axis
        self._x_arr = np.arange(self._duration_plot_samples) \
            / self._scope.sample_rate
        self._plot_handler.setLabel(axis='bottom', text='Time (s)')

    # -------------------------- Main Loop -------------------------
    @copy_doc(_Backend.start_timer)
    def start_timer(self):
        self._timer.start(20)

    @copy_doc(_Backend._update_loop)
    def _update_loop(self):
        super()._update_loop()

        if len(self._scope.ts_list) > 0:
            for k, idx in enumerate(self._scope.selected_channels):
                self._plots[idx].setData(
                    x=self._x_arr,
                    y=self._scope.data_buffer[
                        idx, -self._duration_plot_samples:] + self._offset[k])

            # Update existing events position
            for event in self._trigger_events:
                event.position_buffer = event.position_buffer \
                    - len(self._scope.ts_list) / self._scope.sample_rate
            # Add new events entering the buffer
            self._update_LPT_trigger_events(
                self._scope.trigger_buffer[-len(self._scope.ts_list):])
            # Hide/Remove events exiting window and buffer
            self._clean_up_trigger_events()

            for annot in self._annotations:
                annot.position_buffer = QPointF(
                    annot.position_buffer.x()
                        - len(self._scope.ts_list) / self._scope.sample_rate,
                        0)
            if self._first_click_position is not None:
                position = self._first_click_position.x() - len(self._scope.ts_list) / self._scope.sample_rate
                self._first_click_position.setX(position)
                self._lineItem.setValue(position)

            self._clean_up_annotations()

    # -------------------------- Annotations -----------------------
    @copy_doc(_Backend._clean_up_annotations)
    def _clean_up_annotations(self):
        """
         Hide annotations exiting the plotting window.
        """
        super()._clean_up_annotations()
        for annot in self._annotations:
            if annot.position_plot < 0:
                annot.removeAnnotationFromPlot()

    # ------------------------ Trigger Events ----------------------
    @copy_doc(_Backend._update_LPT_trigger_events)
    def _update_LPT_trigger_events(self, trigger_arr):
        events_trigger_arr_idx = np.where(trigger_arr != 0)[0]
        events_values = trigger_arr[events_trigger_arr_idx]

        for k, event_value in enumerate(events_values):
            position_buffer = self._scope.duration_buffer - \
                (trigger_arr.shape[0] - events_trigger_arr_idx[k]) \
                / self._scope.sample_rate
            position_plot = position_buffer - self._delta_with_buffer

            event = _TriggerEvent(
                event_type='LPT',
                event_value=event_value,
                position_buffer=position_buffer,
                position_plot=position_plot,
                plot_handler=self._plot_handler,
                yRange=self._yRange)

            if position_plot >= 0:
                if event.event_type == 'LPT' and self._show_LPT_trigger_events:
                    event.addEventPlot()

            self._trigger_events.append(event)

    @copy_doc(_Backend._clean_up_trigger_events)
    def _clean_up_trigger_events(self):
        """
         Hide events exiting the plotting window.
        """
        super()._clean_up_trigger_events()
        for event in self._trigger_events:
            if event.position_plot < 0:
                event.removeEventPlot()

    # --------------------------- Events ---------------------------
    @copy_doc(_Backend.close)
    def close(self):
        self._timer.stop()
        self._win.close()

    def _connect_signals_to_slots(self):
        """
        Event handler. Connect QT signals to slots.
        """
        self._plot_handler.getViewBox().scene().sigMouseClicked.connect(
            self.mouse_clicked)

    def mouse_clicked(self, clickEvent):
        if self._recorder_annotation_file is None or clickEvent.button() != 1:
            return

        pen = pg.mkColor(0, 255, 255)
        viewBox = self._plot_handler.getViewBox()

        if self._first_click_position is None:
            self._first_click_position = viewBox.mapSceneToView(
                clickEvent.scenePos())
            self._lineItem = pg.InfiniteLine(
                pos=self._first_click_position.x(), pen=pen)
            self._plot_handler.addItem(self._lineItem)

        else:
            position_buffer = \
                viewBox.mapSceneToView(clickEvent.scenePos())
            position_plot = \
                viewBox.mapSceneToView(clickEvent.scenePos())
            duration = position_plot - self._first_click_position
            position_buffer.setX(position_buffer.x() + self._delta_with_buffer)
            annotation = Annotation(
                self._plot_handler,
                position_buffer=position_buffer,
                position_plot=position_plot,
                duration=duration,
                annotation_description=self._label,
                viewBox=viewBox)

            onset = int(position_buffer.x() * self._scope.sample_rate)
            self._queueTimeStamps.put([self._scope._timestamps_buffer[onset],
                                       duration, self._label])

            self._plot_handler.removeItem(self._lineItem)
            annotation.add()
            self._annotations.append(annotation)
            self._first_click_position = None

    # ------------------------ Update program ----------------------
    @_Backend.xRange.setter
    @copy_doc(_Backend.xRange.setter)
    def xRange(self, xRange):
        self._xRange = xRange
        self._init_variables()
        self._init_canvas()

        for event in self._trigger_events:
            event.position_plot = event.position_buffer-self._delta_with_buffer
            if event.position_plot >= 0:
                if event.event_type == 'LPT' and self._show_LPT_trigger_events:
                    event.addEventPlot()
            else:
                event.removeEventPlot()

        for annot in self._annotations:
            annot.position_plot.setX(annot.position_buffer.x() - self._delta_with_buffer)
            if annot.position_plot.x() >= 0:
                annot.add()
            else:
                annot.remove()

    @_Backend.yRange.setter
    @copy_doc(_Backend.yRange.setter)
    def yRange(self, yRange):
        self._yRange = yRange
        self._init_variables()
        self._init_canvas()

        for event in self._trigger_events:
            event.yRange = self._yRange

    @_Backend.selected_channels.setter
    @copy_doc(_Backend.selected_channels.setter)
    def selected_channels(self, selected_channels):
        plots2remove = [idx for idx in self._selected_channels
                        if idx not in selected_channels]
        plots2add = [idx for idx in selected_channels
                     if idx not in self._selected_channels]
        self._selected_channels = selected_channels
        self._init_variables()
        self._init_canvas()

        for idx in plots2remove:
            self._plot_handler.removeItem(self._plots[idx])
            del self._plots[idx]
        for k, idx in enumerate(plots2add):
            self._plots[idx] = self._plot_handler.plot(
                x=self._x_arr,
                y=self._scope.data_buffer[
                    idx, -self._duration_plot_samples:] + self._offset[k],
                pen=pg.mkColor(self._available_colors[idx, :]))

    @_Backend.show_LPT_trigger_events.setter
    @copy_doc(_Backend.show_LPT_trigger_events.setter)
    def show_LPT_trigger_events(self, show_LPT_trigger_events):
        self._show_LPT_trigger_events = show_LPT_trigger_events
        for event in self._trigger_events:
            if event.position_plot >= 0 and event.event_type == 'LPT':
                if self._show_LPT_trigger_events:
                    event.addEventPlot()
                else:
                    event.removeEventPlot()


@fill_doc
class _TriggerEvent(_Event):
    """
    Class defining a trigger event for the pyqtgraph backend.

    Parameters
    ----------
    %(viewer_event_type)s
    %(viewer_event_value)s
    %(viewer_position_buffer)s
    %(viewer_position_plot)s
    plot_handler : pyqtgraph.PlotItem
        Plot handler.
    yRange : int | float
        Currently set signal range/scale.
    """
    colors = {'LPT': pg.mkColor(0, 255, 0)}

    def __init__(self, event_type, event_value, position_buffer, position_plot,
                 plot_handler, yRange):
        super().__init__(event_type, event_value, position_buffer,
                         position_plot)
        self._plot_handler = plot_handler
        self._yRange = yRange

        self._lineItem = None
        self._textItem = None
        self._plotted = False

    def addEventPlot(self):
        """
        Plots the event on the handler.
        """
        if not self._plotted:
            self._lineItem = pg.InfiniteLine(
                pos=self._position_plot, pen=self.colors[self._event_type])
            self._plot_handler.addItem(self._lineItem)

            self._textItem = pg.TextItem(str(self._event_value),
                                         anchor=(0.5, 0.5),
                                         fill=(0, 0, 0),
                                         color=self.colors[self._event_type])
            self._textItem.setPos(self._position_plot, 1.5*self._yRange)
            self._plot_handler.addItem(self._textItem)
            self._plotted = True

    def removeEventPlot(self):
        """
        Remove the event from the plot handler.
        """
        if self._plotted:
            self._plot_handler.removeItem(self._lineItem)
            self._plot_handler.removeItem(self._textItem)
            self._lineItem = None
            self._textItem = None
            self._plotted = False

    def _update(self):
        """
        Updates the plot handler.
        """
        if self._lineItem is not None:
            self._lineItem.setValue(self._position_plot)
        if self._textItem is not None:
            self._textItem.setPos(self._position_plot, 1.5*self._yRange)

    def __del__(self):
        try:
            self.removeEventPlot()
        except Exception:
            pass

    @property
    @copy_doc(_Event.event_type)
    def event_type(self):
        return self._event_type

    @property
    @copy_doc(_Event.event_value)
    def event_value(self):
        return self._event_value

    @_Event.position_buffer.setter
    @copy_doc(_Event.position_buffer.setter)
    def position_buffer(self, position_buffer):
        _Event.position_buffer.__set__(self, position_buffer)
        self._update()

    @_Event.position_plot.setter
    @copy_doc(_Event.position_plot.setter)
    def position_plot(self, position_plot):
        _Event.position_plot.__set__(self, position_plot)
        self._update()

    @property
    def plotted(self):
        """
        True if the event is displayed, else False.
        """
        return self._plotted

    @property
    def plot_handler(self):
        """
        Plot handler used to display the event.
        """
        return self._plot_handler

    @property
    def yRange(self):
        """
        Signal range/scale used to position the TextItem.
        """
        return self._yRange

    @yRange.setter
    def yRange(self, yRange):
        """
        Impacts the position of the TextItem.
        """
        self._yRange = yRange
        self._update()


class Annot(_Annotation):
    """
    Class defining an annotation for the pyqtgraph backend.

    Parameters
    ----------
    """
    pen = pg.mkColor(0, 255, 255)
    brush = pg.mkBrush(0, 255, 255, 50)

    def __init__(self, description, duration, position_buffer, position_plot,
                 plot_handler):
        super().__init__(description, duration, position_buffer, position_plot)
        self._plot_handler = plot_handler
        self._rectangle = None

    @copy_doc(_Annotation.addAnnotationOnPlot)
    def addAnnotationOnPlot(self):
        super().addAnnotationOnPlot()
        # retrieve position of edges (seconds)
        position_left_edge = self._position_plot - self._duration
        position_right_edge = self._position_plot

        # retrieve height
        height = self._plot_handler.getViewBox().height()

        # create rectangle
        rectangle = QRectF(
            QPointF(position_left_edge, 0),
            QPointF(position_right_edge, height))

        # add rect to plot handler
        self._rectangle = self._plot_handler.getViewBox().scene().addRect(
            rectangle, self.pen, self.brush)

        # change state
        self.plotted = True

    @copy_doc(_Annotation.removeAnnotationFromPlot)
    def removeAnnotationFromPlot(self):
        super().removeAnnotationFromPlot()
        self._plot_handler.getViewBox().scene().removeItem(self._rectangle)
        self._rectangle = None
        self._plotted = False

    def _update(self):
        """
        Updates the plot handler.
        """
        if self._rectangle is None:
            return  # skip, nothing to do

        # retrieve rectangle
        rectangle = self._rectangle.rect()
        position_left_edge = self._position_plot - self._duration

        # clip with Y-axis
        if position_left_edge <= 0:
            _, _, x2, y2 = rectangle.getCoords()
            rectangle.setCoords(0, 0, x2, y2)

        # move left on the plot
        else:
            x1 = self._plot_handler.getViewBox().mapViewToScene(
                QPointF(self._position_plot, 0)).x() - rectangle.width()
            rectangle.moveTo(x1, 0)

        # set rectangle
        self._rectangle.setRect(rectangle)

    @property
    def plot_handler(self):
        """
        Plot handler used to display the event.
        """
        return self._plot_handler

    def __del__(self):
        try:
            self.removeAnnotationFromPlot()
        except Exception:
            pass

    @_Annotation.position_buffer.setter
    @copy_doc(_Annotation.position_buffer.setter)
    def position_buffer(self, position_buffer):
        _Annotation.position_buffer.__set__(self, position_buffer)
        self._update()

    @_Annotation.position_plot.setter
    @copy_doc(_Annotation.position_plot.setter)
    def position_plot(self, position_plot):
        _Annotation.position_plot.__set__(self, position_plot)
        self._update()


class Annotation:

    pens = {'bad': pg.mkColor(255, 0, 255),
              'bad_muscle': pg.mkColor(0, 255, 255)}
    brushs = {'bad': pg.mkBrush(255, 0, 255, 50),
              'bad_muscle': pg.mkBrush(0, 255, 255, 50)}

    def __init__(self, plot_handler, position_buffer, position_plot, duration,
                 annotation_description, viewBox):
        self._plot_handler = plot_handler
        self._position_buffer = position_buffer
        self._position_plot = position_plot
        self._duration = duration
        self._annotation_description = annotation_description
        self._viewBox = viewBox

        self._rect = None
        self._plotted = False

    def add(self):
        try:
            pen = self.pens[self._annotation_description]
            brush = self.brushs[self._annotation_description]
        except KeyError:
            pen = pg.mkColor(255, 0, 0)
            brush = pg.mkBrush(255, 0, 0, 50)

        if not self._plotted:
            position_left = self._viewBox.mapViewToScene(
                self._position_plot - self._duration).x()
            position_right = self._viewBox.mapViewToScene(
                self._position_plot).x()

            rectangle = QRectF(
                QPointF(position_left, 0),
                QPointF(position_right, self._viewBox.height()))
            self._rect = self._plot_handler.getViewBox().scene().addRect(
                rectangle, pen, brush)
            self._plotted=True

    def remove(self):
        if self._plotted:
            self._plot_handler.getViewBox().scene().removeItem(self._rect)
            self._rect = None
            self._plotted = False

    def _update(self):
        if self._rect is not None:
            borderR_pos = self._viewBox.mapViewToScene(self._position_plot).x()
            borderL_pos = borderR_pos - self._rect.rect().width()
            borderL_time = self._viewBox.mapSceneToView(
                QPointF(borderL_pos, 0)).x()

            rect = self._rect.rect()
            if borderL_time <= 0:
                x1 = self._viewBox.mapViewToScene(QPointF(0, 0)).x()
                y1 = 0
                x2 = borderR_pos
                y2 = rect.height()
                rect.setCoords(x1, y1, x2, y2)
            else:
                rect.moveTo(borderL_pos, 0)
            self._rect.setRect(rect)

    @property
    def position_buffer(self):
        return self._position_buffer

    @position_buffer.setter
    def position_buffer(self, position_buffer):
        delta = self._position_buffer.x() - position_buffer.x()
        self._position_buffer = position_buffer
        self._position_plot.setX(self._position_plot.x() - delta)
        self._update()

    @property
    def position_plot(self):
        return self._position_plot

    @position_plot.setter
    def position_plot(self, position_plot):
        self._position_plot = position_plot

    def __del__(self):
        try:
            self.remove()
        except Exception:
            pass
