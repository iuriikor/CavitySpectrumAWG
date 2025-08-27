import numpy
import time
import copy
import logging

from tkinter import *
from M4i6631 import M4i6631

from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)
logger.setLevel(logging.ERROR)


class AOD_gui(Frame):
    def __init__(self, parent, awg_board=None):
        Frame.__init__(self, parent)
        self.root_app = parent
        self.awg_board = awg_board # Variable to store AWG board instance
        ### Top-level GUI elements - just for convenience
        self.interface_def_frame = Frame(self)
        self.control_frame = Frame(self)
        self.trap_params_frame = Frame(self)

        ### App variables
        # Dictionary with TKInter Entry widgets to set trap parameters. Be aware that the format is different from
        # AWG waveform dictionary format. Here it's
        # {Trap number: {'Frequency Ch0, MHz': Entry(), 'Frequency Ch1, MHz': Entry(), 'Amplitude, mV': Entry(), 'Phase, deg': Entry()}}.
        # This is done because there is no reason for me to define amplitude and phase of each tone differently in the GUI.
        self.trap_control_elements_dict = {}

        self.current_wf_params = {} # Current waveform parameters stored in the board object
        self.final_wf_params = {} # Final waveform parameters - used for scanning

        # Get waveform parameters with which AWG board was activated
        self.current_wf_params = self.get_wf_params_from_board()
        self.ch0_num_tones = len(self.current_wf_params[0].keys())
        self.ch1_num_tones = len(self.current_wf_params[1].keys())
        self.num_of_traps = max([self.ch0_num_tones, self.ch1_num_tones])

        # In case the tone does not exist - default parameters
        self.default_tone_params = {
                        "Frequency, Hz": 50e06, # Tone parameters
                        "Amplitude, V": 0.1,
                        # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                        "Phase, rad": 0
                            }
        # Populate app frames with GUI widgets
        self.create_trap_number_ctrl_frame()
        self.create_controls_interface()
        self.create_trap_ctrl_frame()
        self.pack()

    def get_wf_params_from_board(self):
        """
        Helper function to get current waveform parameters from the AWG. Format of the parameters dictionary
        can be seen below.
        :return: Dictionary of current waveform parameters
        """

        # Default value to use when there is no board connected - might be redundant
        current_wf_params = {
            0: {  # Channel 0 index
                0: {  # Tone 0 index
                    "Frequency, Hz": 50e06,  # Tone parameters
                    "Amplitude, V": 0.5,
                    # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                    "Phase, rad": 11.5 / 180 * numpy.pi
                },
                1: {  # Tone 0 index
                    "Frequency, Hz": 55e06,  # Tone parameters
                    "Amplitude, V": 0.5,
                    # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                    "Phase, rad": 11.5 / 180 * numpy.pi
                },
                2: {  # Tone 0 index
                    "Frequency, Hz": 45e06,  # Tone parameters
                    "Amplitude, V": 0.5,
                    # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                    "Phase, rad": 11.5 / 180 * numpy.pi
                }
            },
            1: {  # Channel 1 index
                0: {  # Tone 0 index
                    "Frequency, Hz": 50e06,  # Tone parameters
                    "Amplitude, V": 0.5,
                    # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                    "Phase, rad": 0 / 180 * numpy.pi
                },
                1: {  # Tone 0 index
                    "Frequency, Hz": 45e06,  # Tone parameters
                    "Amplitude, V": 0.5,
                    # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                    "Phase, rad": 0 / 180 * numpy.pi
                },
                2: {  # Tone 0 index
                    "Frequency, Hz": 55e06,  # Tone parameters
                    "Amplitude, V": 0.5,
                    # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                    "Phase, rad": 0 / 180 * numpy.pi
                }
            },
        }
        if self.awg_board is not None:
            current_wf_params = self.awg_board.get_wf_params()
        return current_wf_params

    def sort_trap_controls(self):
        """
        Helper function to sort control elements of the traps. As you increase the number of traps, you can
        populate the new traps with frequencies in any order, and then use this function to order traps
        according to the increasing Channel 0 drive frequency
        :return: None
        """

        sorted_trap_indices = sorted(self.trap_control_elements_dict,
                                     key=lambda x: float(self.trap_control_elements_dict[x]['Frequency Ch0, MHz'].get()))
        new_trap_control_dict = {}
        for new_ind, sorted_ind in enumerate(sorted_trap_indices):
            new_trap_control_dict[new_ind] = self.trap_control_elements_dict[sorted_ind]
        logger.info(f'Old trap sequence: {self.trap_control_elements_dict.keys()}')
        logger.info(f'New trap sequence: {sorted_trap_indices}')
        self.trap_control_elements_dict = new_trap_control_dict
        self.update_wf_params()
        self.create_trap_ctrl_frame()

    def update_trap_ctrl_inputs(self):
        """
        Helper function to update displayed current trap tone parameters with new values taken from the
        self.current_wf_params dictionary. Be aware of different formatting between control
        elements dictionary and waveform definition dictionary.
        :return: None
        """
        # WAVEFORM parameters of AWG channels
        ch0_tone_params = self.current_wf_params.get(0)
        ch1_tone_params = self.current_wf_params.get(1)

        for trap_idx in numpy.arange(self.num_of_traps):
            #
            current_trap_params_ch0 = ch0_tone_params.get(trap_idx, self.default_tone_params)
            current_trap_params_ch1 = ch1_tone_params.get(trap_idx, self.default_tone_params)

            logger.info(f"Trap {trap_idx} \n ch0: {current_trap_params_ch0["Frequency, Hz"]/1e06} MHz \n ch1: {current_trap_params_ch1["Frequency, Hz"]/1e06} MHz ")
            self.trap_control_elements_dict[trap_idx]["Frequency Ch0, MHz"].delete(0, END) # Clears text in the entry
            self.trap_control_elements_dict[trap_idx]["Frequency Ch0, MHz"].insert(END,
                                                                                f'{current_trap_params_ch0["Frequency, Hz"]/1e06}')

            self.trap_control_elements_dict[trap_idx]["Frequency Ch1, MHz"].delete(0, END)
            self.trap_control_elements_dict[trap_idx]["Frequency Ch1, MHz"].insert(END,
                                                                                f'{current_trap_params_ch1["Frequency, Hz"] / 1e06}')

            self.trap_control_elements_dict[trap_idx]["Amplitude, mV"].delete(0, END)
            self.trap_control_elements_dict[trap_idx]["Amplitude, mV"].insert(END,
                                                                            f'{current_trap_params_ch0["Amplitude, V"] * 1e03}')

            self.trap_control_elements_dict[trap_idx]["Phase, deg"].delete(0, END)
            self.trap_control_elements_dict[trap_idx]["Phase, deg"].insert(END,
                                                                        f'{current_trap_params_ch0["Phase, rad"]/numpy.pi*180}')

    def populate_trap_ctrl_dict(self):
        """
        Helper function to create widgets to manually define trap parameters, and store them in the
        self.trap_control_elements_dict variable.
        :return: None
        """

        self.trap_control_elements_dict = {}
        for trap_idx in numpy.arange(self.num_of_traps):
            self.trap_control_elements_dict[trap_idx] = {}

            self.trap_control_elements_dict[trap_idx]["Frequency Ch0, MHz"] = \
            Entry(self.trap_params_frame, width=20)

            self.trap_control_elements_dict[trap_idx]["Frequency Ch1, MHz"] = \
                Entry(self.trap_params_frame, width=20)

            self.trap_control_elements_dict[trap_idx]["Amplitude, mV"] = \
                Entry(self.trap_params_frame, width=20)

            self.trap_control_elements_dict[trap_idx]["Phase, deg"] = \
                Entry(self.trap_params_frame, width=20)
        self.update_trap_ctrl_inputs()

    def create_trap_ctrl_frame(self):
        """
        Place the widgets for manual trap definition, created in populate_trap_ctrl_dict, into the frame containing
        these elements. This is done just to separate the code by its functionality.
        :return:
        """
        self.trap_params_frame.destroy() # Delete the current frame, otherwise new elements will be displayed just on top of the old ones
        self.trap_params_frame = Frame(self) # Create new clean frame object
        # Place labels for widgets
        Label(self.trap_params_frame, text='Freq Ch0, MHz').grid(row=1, column=0)
        Label(self.trap_params_frame, text='Freq Ch1, MHz').grid(row=2, column=0)
        Label(self.trap_params_frame, text='Amplitude, mV').grid(row=3, column=0)
        Label(self.trap_params_frame, text='Phase, deg.').grid(row=4, column=0)

        self.num_of_traps = int(self.num_traps_entry.get())
        self.populate_trap_ctrl_dict()
        # Place trap control widgets for each trap
        for trap_idx in numpy.arange(self.num_of_traps):
            Label(self.trap_params_frame, text=f'Trap {trap_idx}').grid(row=0, column=1 + trap_idx)
            self.trap_control_elements_dict[trap_idx]["Frequency Ch0, MHz"].grid(row=1, column=1 + trap_idx)
            self.trap_control_elements_dict[trap_idx]["Frequency Ch1, MHz"].grid(row=2, column=1 + trap_idx)
            self.trap_control_elements_dict[trap_idx]["Amplitude, mV"].grid(row=3, column=1 + trap_idx)
            self.trap_control_elements_dict[trap_idx]["Phase, deg"].grid(row=4, column=1 + trap_idx)

        self.trap_params_frame.grid(row=1, column=0)

    def create_controls_interface(self):
        """
        Helper function to create frame containing control elements, such as currently used segment and all the buttons
        :return: None
        """

        Label(self.control_frame, text="Segment used").grid(row=2, column=1, sticky=W)
        self.mem_segment_used = Entry(self.control_frame, width=20)
        self.mem_segment_used.grid(row=3, column=1, sticky=W)
        self.mem_segment_used.insert(0, self.awg_board.current_segment)

        btn_w = 20
        Button(self.control_frame, text="Send Data", command=self.push_updates_to_board, width = btn_w).grid(row=5, column=1, sticky=E)
        Button(self.control_frame, text="Quit", command=self.close, width = btn_w).grid(row=11, column=1, sticky=E)
        Button(self.control_frame, text="Move Frequencies", command=self.create_freq_scan_window, width = btn_w).grid(row=7, column=1, sticky=E)
        Button(self.control_frame, text="Move Traps (same rate)", command=self.create_window_move_traps_together, width=btn_w).grid(row=7, column=1, sticky=E)
        Button(self.control_frame, text="Move Traps (accordion)", command=self.create_window_move_traps_accordion, width=btn_w).grid(row=8, column=1, sticky=E)
        Button(self.control_frame, text="Move Phase", command=self.create_phase_scan_window, width = btn_w).grid(row=10, column=1, sticky=E)

        self.control_frame.grid(row=0, column=1, rowspan=2)

    def create_trap_number_ctrl_frame(self):
        """
        Frame containing controls for creating interface for N traps. Again, this is here just to separate the code.
        :return: None
        """
        # Number_Channel
        num_traps_lbl = Label(self.interface_def_frame, text="Number of traps:")
        num_traps_lbl.grid(row=0, column=0, sticky=W)
        self.num_traps_entry = Entry(self.interface_def_frame, width=10)
        self.num_traps_entry.insert(-1, f'{self.num_of_traps}')
        self.num_traps_entry.grid(row=0, column=1)

        Button(self.interface_def_frame, text="Create Interface", command=self.create_trap_ctrl_frame).grid(row=0, column=2)
        Button(self.interface_def_frame, text="Sort traps", command=self.sort_trap_controls).grid(row=0, column=4)

        self.interface_def_frame.grid(row=0, column=0)

    def create_freq_scan_window(self):
        """
        Creates a new window with widgets to define frequency scan parameters.
        :return:
        """

        freq_scan_window = Toplevel(self.root_app) # Toplevel just pops a window on top of the main window
        freq_scan_window.title("Frequency Scan")
        freq_ctrl_frame = Frame(freq_scan_window) # Just for utility, I place elements in a grid in the Frame, then pack Frame in the window
        freq_ctrl_frame.pack() # Actually, I first pack the frame, and then populate it, but order really does not matter

        self.end_freq_controls = {0: {}, 1: {}} # Separate widget storage for channel 0 and channel 1

        Label(freq_ctrl_frame, text='Current frequency, MHz').grid(row=0, column=1)
        Label(freq_ctrl_frame, text='Final frequency, MHz').grid(row=0, column=2)
        for trap_idx in numpy.arange(self.num_of_traps):
            ch0_start_freq = self.current_wf_params[0][trap_idx]['Frequency, Hz']/1e06
            ch1_start_freq = self.current_wf_params[1][trap_idx]['Frequency, Hz']/1e06

            Label(freq_ctrl_frame, text=f'Trap {trap_idx}').grid(row=1+3*trap_idx, column=0)
            # Channel 0 - I overwrite this variable because this is just to show current settings
            curr_freq = Entry(freq_ctrl_frame)
            curr_freq.grid(row=1+3*trap_idx, column=1)
            curr_freq.insert(-1, f'{ch0_start_freq}')
            curr_freq.configure(state='disabled')
            # Channel 1
            curr_freq = Entry(freq_ctrl_frame)
            curr_freq.grid(row=1 + 3 * trap_idx + 1, column=1)
            curr_freq.insert(-1, f'{ch1_start_freq}')
            curr_freq.configure(state='disabled')
            # Blank space
            Label(freq_ctrl_frame, text='').grid(row=1+3*trap_idx+2, column=1)

            # Channel 0 final frequency
            self.end_freq_controls[0][trap_idx] = Entry(freq_ctrl_frame)
            self.end_freq_controls[0][trap_idx].insert(-1, f'{ch0_start_freq}')
            self.end_freq_controls[0][trap_idx].grid(row=1+3*trap_idx,column=2)
            # Channel 1 final frequency
            self.end_freq_controls[1][trap_idx] = Entry(freq_ctrl_frame)
            self.end_freq_controls[1][trap_idx].insert(-1, f'{ch1_start_freq}')
            self.end_freq_controls[1][trap_idx].grid(row=1+3*trap_idx+1, column=2)

        Label(freq_ctrl_frame, text='Step size, kHz:').grid(row=0, column=6)
        self.step_size_entry = Entry(freq_ctrl_frame)
        self.step_size_entry.insert(-1, f'10')
        self.step_size_entry.grid(row=1, column=6)

        Label(freq_ctrl_frame, text='Delay between steps, s:').grid(row=3, column=6)
        self.delay_entry = Entry(freq_ctrl_frame)
        self.delay_entry.insert(-1, f'0.4')
        self.delay_entry.grid(row=4, column=6)

        Button(freq_ctrl_frame, text='Start scan', command=self.scan_frequency).grid(row=6, column=6)

    def scan_frequency(self):
        """
        I am going to do this the same way it was done in the old code. First I determine which tone needs to change
        its frequency the most. Then from this I determine the number of steps I need to get to the final frequency.
        If there is more than one tone frequency we need to scan, the step size for it is adapted such that the scans
        are finished in the same number of steps.

        :return:
        """

        scan_step_hz = float(self.step_size_entry.get())*1e03
        scan_delay_s = float(self.delay_entry.get())

        freq_diff_tones = {0: {}, 1: {}} # I store difference between final and starting frequencies, per tone per channel
        max_steps_ch = -1 # These I ended up not using, but I'll keep them here just in case
        max_steps_trap = -1
        max_freq_diff = -1
        for trap_idx in numpy.arange(self.num_of_traps):
            freq_diff_tones[0][trap_idx] = float(self.end_freq_controls[0][trap_idx].get()) * 1e06 - \
                                           self.current_wf_params[0][trap_idx]['Frequency, Hz']
            freq_diff_tones[1][trap_idx] = float(self.end_freq_controls[1][trap_idx].get()) * 1e06 - \
                                           self.current_wf_params[1][trap_idx]['Frequency, Hz']

            if numpy.abs(freq_diff_tones[0][trap_idx]) > max_freq_diff:
                max_freq_diff = numpy.abs(freq_diff_tones[0][trap_idx])
                max_steps_ch = 0
                max_steps_trap = trap_idx
            if numpy.abs(freq_diff_tones[1][trap_idx]) > max_freq_diff:
                max_freq_diff = numpy.abs(freq_diff_tones[1][trap_idx])
                max_steps_ch = 1
                max_steps_trap = trap_idx

        num_steps_freq_scan = int(max_freq_diff//scan_step_hz)
        last_step_time = 0
        for scan_step in numpy.arange(num_steps_freq_scan):
            logger.info("Scanning: step {:d}/{:d}".format(scan_step+1, num_steps_freq_scan))
            for trap_idx in numpy.arange(self.num_of_traps):
                self.current_wf_params[0][trap_idx]['Frequency, Hz'] += freq_diff_tones[0][
                                                                            trap_idx] / num_steps_freq_scan
                self.current_wf_params[1][trap_idx]['Frequency, Hz'] += freq_diff_tones[1][
                                                                            trap_idx] / num_steps_freq_scan
            # Delay
            while (time.time() - last_step_time) < scan_delay_s:
                time.sleep(0)
            last_step_time = time.time()
            logger.debug(f'Waveform parameters: {self.current_wf_params}')

            err = self.awg_board.set_output_wf_params(self.current_wf_params)
            if err:
                logger.error("Failed to change output waveform parameters")
                return err
        self.update_trap_ctrl_inputs()
        return err

    def create_phase_scan_window(self):

        phase_scan_window = Toplevel(self.root_app)
        phase_scan_window.title("Frequency Scan")
        phase_ctrl_frame = Frame(phase_scan_window)
        phase_ctrl_frame.pack()

        self.phase_scan_controls = []

        Label(phase_ctrl_frame, text='Current phase, deg').grid(row=0, column=1)
        Label(phase_ctrl_frame, text='Final phase, deg').grid(row=0, column=2)
        for trap_idx in numpy.arange(self.num_of_traps):
            starting_phase = self.current_wf_params[1][trap_idx]['Phase, rad']

            Label(phase_ctrl_frame, text=f'Trap {trap_idx}').grid(row=1+3*trap_idx, column=0)
            # Initial phase display
            curr_phase = Entry(phase_ctrl_frame)
            curr_phase.grid(row=1+3*trap_idx, column=1)
            curr_phase.insert(0, f'{starting_phase}')
            curr_phase.configure(state='disabled')

            # Final phase
            self.phase_scan_controls.append(Entry(phase_ctrl_frame))
            self.phase_scan_controls[trap_idx].insert(-1, f'{starting_phase}')
            self.phase_scan_controls[trap_idx].grid(row=1+3*trap_idx,column=2)


        Label(phase_ctrl_frame, text='Step size, deg:').grid(row=0, column=6)

        # Overwrite class variable with step control, since we're only doing one scan at a time
        self.step_size_entry = Entry(phase_ctrl_frame)
        self.step_size_entry.insert(-1, f'10')
        self.step_size_entry.grid(row=1, column=6)
        # Same with delay
        Label(phase_ctrl_frame, text='Delay between steps, s:').grid(row=3, column=6)
        self.delay_entry = Entry(phase_ctrl_frame)
        self.delay_entry.insert(-1, f'0.4')
        self.delay_entry.grid(row=4, column=6)

        Button(phase_ctrl_frame, text='Start scan', command=self.scan_phase).grid(row=6, column=6)

    def scan_phase(self):
        """
        I am going to do this the same way it was done in the old code. First I determine which tone needs to change
        its phase the most. Then from this I determine the number of steps I need to get to the final phase.
        If there is more than one tone phase we need to scan, the step size for it is adapted such that the scans
        are finished in the same number of steps.

        :return:
        """

        scan_step_rad = float(self.step_size_entry.get())/180*numpy.pi
        scan_delay_s = float(self.delay_entry.get())

        phase_change_per_trap = numpy.zeros(self.num_of_traps)
        max_steps_ch = -1
        max_steps_trap = -1
        max_freq_diff = -1
        for trap_idx in numpy.arange(self.num_of_traps):
            phase_change_per_trap[trap_idx] = float(self.phase_scan_controls[trap_idx].get())/180*numpy.pi - \
                                           self.current_wf_params[1][trap_idx]['Phase, rad']

        num_steps_phase_scan = int(numpy.max(phase_change_per_trap)//scan_step_rad)
        last_step_time = 0
        for scan_step in numpy.arange(num_steps_phase_scan):
            logger.info("Scanning: step {:d}/{:d}".format(scan_step+1, num_steps_phase_scan))
            for trap_idx in numpy.arange(self.num_of_traps):
                # Phase is only changed on channel 1
                self.current_wf_params[1][trap_idx]['Phase, rad'] += phase_change_per_trap[
                                                                            trap_idx] / num_steps_phase_scan
            # Delay
            while (time.time() - last_step_time) < scan_delay_s:
                time.sleep(0)
            last_step_time = time.time()
            logger.debug(f'Waveform parameters: {self.current_wf_params}')

            err = self.awg_board.set_output_wf_params(self.current_wf_params)
            if err:
                logger.error("Failed to change output waveform parameters")
                return err
        self.update_trap_ctrl_inputs()
        return err

    def create_window_move_traps_together(self):
        """
        Creates a new window with widgets to define frequency scan parameters.
        This window is intended to move the traps to the same side at the same rate.
        Later this and other waveform scan windows may be unified into a single multiparameter
        scan interface.
        :return:
        """

        freq_scan_window = Toplevel(self.root_app) # Toplevel just pops a window on top of the main window
        freq_scan_window.title("Move traps at the same rate")
        freq_ctrl_frame = Frame(freq_scan_window) # Just for utility, I place elements in a grid in the Frame, then pack Frame in the window
        freq_ctrl_frame.pack() # Actually, I first pack the frame, and then populate it, but order really does not matter

        self.end_freq_controls = {0: {}, 1: {}} # Separate widget storage for channel 0 and channel 1

        Label(freq_ctrl_frame, text='Current frequency, MHz').grid(row=1, column=1)
        Label(freq_ctrl_frame, text='Final frequency, MHz').grid(row=1, column=2)
        Label(freq_ctrl_frame, text="Trap drive shift, MHz:").grid(row=0, column=1)
        self.detuning_entry = Entry(freq_ctrl_frame)
        self.detuning_entry.insert(-1, '1')
        self.detuning_entry.grid(row=0, column=2)

        for trap_idx in numpy.arange(self.num_of_traps):
            ch0_start_freq = self.current_wf_params[0][trap_idx]['Frequency, Hz']/1e06
            ch1_start_freq = self.current_wf_params[1][trap_idx]['Frequency, Hz']/1e06

            Label(freq_ctrl_frame, text=f'Trap {trap_idx}').grid(row=1+3*trap_idx, column=0)
            # Channel 0 - I overwrite this variable because this is just to show current settings
            curr_freq = Entry(freq_ctrl_frame)
            curr_freq.grid(row=2+3*trap_idx, column=1)
            curr_freq.insert(-1, f'{ch0_start_freq}')
            curr_freq.configure(state='disabled')
            # Channel 1
            curr_freq = Entry(freq_ctrl_frame)
            curr_freq.grid(row=2 + 3 * trap_idx + 1, column=1)
            curr_freq.insert(-1, f'{ch1_start_freq}')
            curr_freq.configure(state='disabled')
            # Blank space
            Label(freq_ctrl_frame, text='').grid(row=2+3*trap_idx+2, column=1)

            # Channel 0 final frequency
            self.end_freq_controls[0][trap_idx] = Entry(freq_ctrl_frame)
            self.end_freq_controls[0][trap_idx].insert(-1, f'{ch0_start_freq+float(self.detuning_entry.get())}')
            self.end_freq_controls[0][trap_idx].grid(row=1+3*trap_idx,column=2)
            # Channel 1 final frequency
            self.end_freq_controls[1][trap_idx] = Entry(freq_ctrl_frame)
            self.end_freq_controls[1][trap_idx].insert(-1, f'{ch1_start_freq-float(self.detuning_entry.get())}')
            self.end_freq_controls[1][trap_idx].grid(row=1+3*trap_idx+1, column=2)

        Label(freq_ctrl_frame, text='Step size, kHz:').grid(row=0, column=6)
        self.step_size_entry = Entry(freq_ctrl_frame)
        self.step_size_entry.insert(-1, f'10')
        self.step_size_entry.grid(row=1, column=6)

        Label(freq_ctrl_frame, text='Delay between steps, s:').grid(row=3, column=6)
        self.delay_entry = Entry(freq_ctrl_frame)
        self.delay_entry.insert(-1, f'0.4')
        self.delay_entry.grid(row=4, column=6)

        Button(freq_ctrl_frame, text='Update frequencies', command=self.update_freq_together).grid(row=5, column=6)
        Button(freq_ctrl_frame, text='Start scan', command=self.scan_frequency).grid(row=6, column=6)

    def update_freq_together(self):
        """
        Helper function to update the final frequencies of the RF tones for each trap in order to move traps to
        the same side at the same rate.
        :return:
        """
        for trap_idx in numpy.arange(self.num_of_traps):
            ch0_start_freq = self.current_wf_params[0][trap_idx]['Frequency, Hz']/1e06
            ch1_start_freq = self.current_wf_params[1][trap_idx]['Frequency, Hz']/1e06
            # Channel 0 final frequency
            self.end_freq_controls[0][trap_idx].delete(0, END)
            self.end_freq_controls[0][trap_idx].insert(-1, f'{ch0_start_freq+float(self.detuning_entry.get())}')
            self.end_freq_controls[0][trap_idx].grid(row=1+3*trap_idx,column=2)
            # Channel 1 final frequency
            self.end_freq_controls[1][trap_idx].delete(0, END)
            self.end_freq_controls[1][trap_idx].insert(-1, f'{ch1_start_freq-float(self.detuning_entry.get())}')
            self.end_freq_controls[1][trap_idx].grid(row=1+3*trap_idx+1, column=2)

    def create_window_move_traps_accordion(self):
        """
        Creates a new window with widgets to define frequency scan parameters.
        This window is intended to move the traps in "acordion lattice" way, i.e. the outward traps move the most,
        the central (50 MHz-50 MHz) trap stays at the same position, and the others move proportionally to their position.
        Later this and other waveform scan windows may be unified into a single multiparameter
        scan interface.
        :return:
        """
        freq_scan_window = Toplevel(self.root_app) # Toplevel just pops a window on top of the main window
        freq_scan_window.title("Move traps at the same rate")
        freq_ctrl_frame = Frame(freq_scan_window) # Just for utility, I place elements in a grid in the Frame, then pack Frame in the window
        freq_ctrl_frame.pack() # Actually, I first pack the frame, and then populate it, but order really does not matter

        self.end_freq_controls = {0: {}, 1: {}} # Separate widget storage for channel 0 and channel 1

        Label(freq_ctrl_frame, text='Current frequency, MHz').grid(row=1, column=1)
        Label(freq_ctrl_frame, text='Final frequency, MHz').grid(row=1, column=2)
        Label(freq_ctrl_frame, text="MAXIMUM drive shift, MHz:").grid(row=0, column=1)
        self.detuning_entry = Entry(freq_ctrl_frame)
        self.detuning_entry.insert(-1, '1')
        self.detuning_entry.grid(row=0, column=2)
        trap_freq_shift = numpy.linspace(-float(self.detuning_entry.get()),
                                         float(self.detuning_entry.get()),
                                         self.num_of_traps)

        for trap_idx in numpy.arange(self.num_of_traps):
            ch0_start_freq = self.current_wf_params[0][trap_idx]['Frequency, Hz']/1e06
            ch1_start_freq = self.current_wf_params[1][trap_idx]['Frequency, Hz']/1e06

            Label(freq_ctrl_frame, text=f'Trap {trap_idx}').grid(row=1+3*trap_idx, column=0)
            # Channel 0 - I overwrite this variable because this is just to show current settings
            curr_freq = Entry(freq_ctrl_frame)
            curr_freq.grid(row=2+3*trap_idx, column=1)
            curr_freq.insert(-1, f'{ch0_start_freq}')
            curr_freq.configure(state='disabled')
            # Channel 1
            curr_freq = Entry(freq_ctrl_frame)
            curr_freq.grid(row=2 + 3 * trap_idx + 1, column=1)
            curr_freq.insert(-1, f'{ch1_start_freq}')
            curr_freq.configure(state='disabled')
            # Blank space
            Label(freq_ctrl_frame, text='').grid(row=2+3*trap_idx+2, column=1)

            # Channel 0 final frequency
            self.end_freq_controls[0][trap_idx] = Entry(freq_ctrl_frame)
            self.end_freq_controls[0][trap_idx].insert(-1, f'{ch0_start_freq+trap_freq_shift[trap_idx]}')
            self.end_freq_controls[0][trap_idx].grid(row=1+3*trap_idx,column=2)
            # Channel 1 final frequency
            self.end_freq_controls[1][trap_idx] = Entry(freq_ctrl_frame)
            self.end_freq_controls[1][trap_idx].insert(-1, f'{ch1_start_freq-trap_freq_shift[trap_idx]}')
            self.end_freq_controls[1][trap_idx].grid(row=1+3*trap_idx+1, column=2)

        Label(freq_ctrl_frame, text='Step size, kHz:').grid(row=0, column=6)
        self.step_size_entry = Entry(freq_ctrl_frame)
        self.step_size_entry.insert(-1, f'10')
        self.step_size_entry.grid(row=1, column=6)

        Label(freq_ctrl_frame, text='Delay between steps, s:').grid(row=3, column=6)
        self.delay_entry = Entry(freq_ctrl_frame)
        self.delay_entry.insert(-1, f'0.4')
        self.delay_entry.grid(row=4, column=6)

        Button(freq_ctrl_frame, text='Update frequencies', command=self.update_freq_accordion).grid(row=5, column=6)
        Button(freq_ctrl_frame, text='Start scan', command=self.scan_frequency).grid(row=6, column=6)

    def update_freq_accordion(self):
        """
        Helper function to update the final frequencies of the RF tones for each trap in order to move traps in
        "accordion lattice" way.
        :return:
        """
        trap_freq_shift = numpy.linspace(-float(self.detuning_entry.get()),
                                         float(self.detuning_entry.get()),
                                         self.num_of_traps)
        for trap_idx in numpy.arange(self.num_of_traps):
            ch0_start_freq = self.current_wf_params[0][trap_idx]['Frequency, Hz']/1e06
            ch1_start_freq = self.current_wf_params[1][trap_idx]['Frequency, Hz']/1e06
            # Channel 0 final frequency
            self.end_freq_controls[0][trap_idx].delete(0, END)
            self.end_freq_controls[0][trap_idx].insert(-1, f'{ch0_start_freq+trap_freq_shift[trap_idx]}')
            self.end_freq_controls[0][trap_idx].grid(row=1+3*trap_idx,column=2)
            # Channel 1 final frequency
            self.end_freq_controls[1][trap_idx].delete(0, END)
            self.end_freq_controls[1][trap_idx].insert(-1, f'{ch1_start_freq-trap_freq_shift[trap_idx]}')
            self.end_freq_controls[1][trap_idx].grid(row=1+3*trap_idx+1, column=2)

    def update_wf_params(self):
        """
        Function to update the dictionary defining AWG RF tones FROM MANUAL CONTROL INTERFACE.
        :return:
        """
        new_wf_params = {0: {}, 1: {}}
        for trap_idx in numpy.arange(self.num_of_traps):
            new_wf_params[0][trap_idx] = {}
            new_wf_params[1][trap_idx] = {}
            new_wf_params[0][trap_idx]['Frequency, Hz'] = float(
                self.trap_control_elements_dict[trap_idx]["Frequency Ch0, MHz"].get()) * 1e06
            new_wf_params[1][trap_idx]['Frequency, Hz'] = float(
                self.trap_control_elements_dict[trap_idx]["Frequency Ch1, MHz"].get()) * 1e06

            new_wf_params[0][trap_idx]['Amplitude, V'] = float(
                self.trap_control_elements_dict[trap_idx]["Amplitude, mV"].get())*1e-03
            new_wf_params[1][trap_idx]['Amplitude, V'] = float(
                self.trap_control_elements_dict[trap_idx]["Amplitude, mV"].get()) * 1e-03

            new_wf_params[0][trap_idx]['Phase, rad'] = 0
            new_wf_params[1][trap_idx]['Phase, rad'] = float(
                self.trap_control_elements_dict[trap_idx]["Phase, deg"].get()) * numpy.pi/180

        logger.info("New WF Parameters: {}".format(new_wf_params))
        self.current_wf_params = new_wf_params

    def push_updates_to_board(self):
        """
        Push updated waveform parameters dictionary to the AWG board and update the output.
        :return:
        """
        self.update_wf_params()
        t1 = time.time()
        err = self.awg_board.set_output_wf_params(self.current_wf_params)
        t2 = time.time()
        logger.info(f"Setting WF took {(t2-t1)*1e03} ms")
        if err:
            logger.error("Failed to change output waveform parameters")
        self.mem_segment_used.delete(0, END)
        self.mem_segment_used.insert(0, self.awg_board.current_segment)
        return err

    def close(self):
        """
        Turn off AWG card and close the main window.
        :return: None
        """
        self.awg_board.card_turn_off()
        self.root_app.destroy()


if __name__ == "__main__":
    wf_params_startup = {
        0: {  # Channel 0 index
            0: {  # Tone 0 index
                "Frequency, Hz": 45e06,  # Tone parameters
                "Amplitude, V": 0.1,
                # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                "Phase, rad": 0
            },
            1: {  # Tone 1 index
                "Frequency, Hz": 55e06,  # Tone parameters
                "Amplitude, V": 0.1,
                # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                "Phase, rad": 0
            }
        },
        1: {  # Channel 1 index
            0: {  # Tone 0 index
                "Frequency, Hz": 55e06,  # Tone parameters
                "Amplitude, V": 0.1,
                "Phase, rad": 0
            },
            1: {  # Tone 1 index
                "Frequency, Hz": 45e06,  # Tone parameters
                "Amplitude, V": 0.1,
                "Phase, rad": 0
            }
        }
    }
    awg_m4i6631 = M4i6631(address=b'/dev/spcm0',
                   channelNum=2,
                   sampleRate=500,
                   referenceClock=True,
                   referenceClockFrequency=100e06,
                   clockOut=False,
                   wf_params_default=wf_params_startup,
                   f_res_desired=1000)
    awg_m4i6631.card_turn_on()

    main_window = Tk()
    main_window.title("AOD Driver")
    app = AOD_gui(main_window, awg_m4i6631)
    main_window.mainloop()