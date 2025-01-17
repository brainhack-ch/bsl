import time

import mne
import pytest

from bsl import StreamRecorder, StreamPlayer, logger, set_log_level
from bsl.datasets import eeg_resting_state
from bsl.triggers.lpt import TriggerArduino2LPT
from bsl.utils._tests import (requires_eeg_resting_state_dataset,
                              requires_lpt, requires_usb2lpt,
                              requires_arduino2lpt)


set_log_level('INFO')
logger.propagate = True

# TODO: Compact the syntax into one parametized function.


@requires_lpt
@requires_eeg_resting_state_dataset
def test_lpt(tmp_path, portaddr):
    """Testing for build-in LPT port."""
    # TODO
    pass


@requires_usb2lpt
@requires_eeg_resting_state_dataset
def test_usblpt(tmp_path, caplog):
    """Testing for USB to LPT converter."""
    # TODO
    pass


@requires_arduino2lpt
@requires_eeg_resting_state_dataset
def test_arduino2lpt(tmp_path, caplog):
    """Testing for Arduino to LPT converter."""
    # Test trigger
    with StreamPlayer('StreamPlayer', eeg_resting_state.data_path()):
        recorder = StreamRecorder(record_dir=tmp_path, fname='test',
                                  stream_name='StreamPlayer', fif_subdir=False)

        trigger = TriggerArduino2LPT(verbose=True)
        time.sleep(0.5)
        assert trigger.verbose
        trigger.verbose = False

        assert trigger.signal(1)
        time.sleep(0.1)
        assert trigger.signal(2)

        trigger.close()
        time.sleep(0.5)
        recorder.stop()

    raw = mne.io.read_raw_fif(tmp_path / 'test-StreamPlayer-raw.fif')
    events = mne.find_events(raw, stim_channel='TRIGGER')
    assert events.shape == (2, 3)
    assert (events[:, 2] == [1, 2]).all()

    # Test delay
    trigger = TriggerArduino2LPT(delay=100, verbose=False)
    time.sleep(0.1)
    assert trigger.signal(1)
    assert not trigger.signal(2)
    assert 'new signal before the end of the last' in caplog.text

    # Test property setters
    time.sleep(0.2)
    with pytest.raises(AttributeError, match="can't set attribute"):
        trigger.delay = 50
    assert trigger.delay == 100
