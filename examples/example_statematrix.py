"""
Example of how to use the statematrix module.
"""

from phonotaxis import statematrix
import numpy as np

INPUTS = ['IZ', 'L', 'R']
OUTPUTS = ['ValveL', 'ValveR']

SOUND_ID = 1
CORRECT_PORT = 'R'  # For example, right port
VALVE_DURATION = 0.2

sm = statematrix.StateMatrix(inputs=INPUTS, outputs=OUTPUTS)

sm.add_state(name='wait_for_init_zone', statetimer=np.inf,
                    transitions={'IZin':'play_sound'},
                    outputsOff=['ValveL', 'ValveR'])
sm.add_state(name='play_sound', statetimer=0.5,
                    transitions={'Tup':'wait_for_response'},
                    integerOut=SOUND_ID)
sm.add_state(name='wait_for_response', statetimer=5,
                    transitions={CORRECT_PORT+'in':'rewardOn', 'Tup':'END'},
                    outputsOff=['ValveL', 'ValveR'])
sm.add_state(name='rewardOn', statetimer=VALVE_DURATION,
                    transitions={'Tup':'rewardOff'},
                    outputsOn=['Valve'+CORRECT_PORT])
sm.add_state(name='rewardOff', statetimer=0,
                    transitions={'Tup':'END'},
                    outputsOff=['Valve'+CORRECT_PORT])

print(sm)