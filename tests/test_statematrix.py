"""
Test statematrix module.
"""

from phonotaxis import statematrix

sm = statematrix.StateMatrix(inputs={'C':0, 'L':1, 'R':2},
                    outputs={'centerLED':0, 'leftLED':1, 'rightLED':2})

sm.add_state(name='wait_for_cpoke', statetimer=2,
            transitions={'Cin':'stim_on', 'Tup':'stim_on'},
            outputsOff=['centerLED'])
sm.add_state(name='stim_on', statetimer=0.5,
            transitions={'Tup':'wait_for_cpoke'},
            outputsOn=['centerLED'])
print(sm)
