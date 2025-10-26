"""
Test statematrix module.
"""

from phonotaxis import statematrix

if 0:
    sm = statematrix.StateMatrix(inputs=['C', 'L', 'R'],
                        outputs=['centerLED', 'leftLED', 'rightLED'])

    sm.add_state(name='wait_for_cpoke', statetimer=2,
                transitions={'Cin':'stim_on', 'Tup':'stim_on'},
                outputsOff=['centerLED'])
    sm.add_state(name='stim_on', statetimer=0.5,
                transitions={'Tup':'wait_for_cpoke'},
                outputsOn=['centerLED'])
    print(sm)


if 1:
    import numpy as np
    valve_duration = 0.2
    correct_port = 'R'  # 'L' or 'R'
    INPUTS = ['IZ', 'L', 'R']
    OUTPUTS = ['ValveL', 'ValveR']
    sm = statematrix.StateMatrix(inputs=INPUTS, outputs=OUTPUTS)
    sm.add_state(name='wait_for_init_zone', statetimer=np.inf,
                        transitions={'IZin':'play_sound'},
                        outputsOff=['ValveL', 'ValveR'])
    sm.add_state(name='play_sound', statetimer=0.5,
                        transitions={'Tup':'wait_for_response'})
    sm.add_state(name='wait_for_response', statetimer=5,
                        transitions={correct_port+'in':'rewardOn',
                                    'Tup':'END'},
                        outputsOff=['ValveL', 'ValveR'])
    sm.add_state(name='rewardOn', statetimer=valve_duration,
                        transitions={'Tup':'rewardOff'},
                        outputsOn=['Valve'+correct_port])
    sm.add_state(name='rewardOff', statetimer=0,
                        transitions={'Tup':'END'},
                        outputsOff=['Valve'+correct_port])
    print(sm)