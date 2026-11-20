# Japanese native Oedo Town face textures

Reported in Oedo Town South (map `0x161`) and West (`0x15F`). Some faces alternate between visible and blank. The cause matches the robot defect: the game already rebases the graphics operands against each NPC's loaded model. Code generation was rebasing some operands against the executing overlay first.

The setup at `0x80229A50` stores three texture operands at actor offsets `0x90`, `0x9C`, and `0xA0`. The setup and expression updates pass the selected operand to `0x8021F4D4`, which adds the model base and subtracts `0x08000000`. The active address is written to the object slot for RSP segment B. A correct operand can alternate with an incorrectly relocated one, so the face can reappear even on the original native build.

The Japanese rev 0 relocation metadata now leaves all four proven graphics operands in executable `file_59` in their original form.

| Actor / model | Model file | Operand | HI16 / LO16 sites |
| --- | --- | --- | --- |
| `0x02C0` | `0x0275` | `0x08001B10` | `0x0800036C` / `0x08000370` |
| `0x02C1` | `0x0276` | `0x08001710` | `0x08000420` / `0x08000434` |
| `0x02C6` | `0x027A` | `0x080018B0` | `0x08001524` / `0x08001534` |
| `0x02C8` | `0x027C` | `0x080019A0` | `0x08001868` / `0x0800187C` |

## Native comparison

Compared the robot-only build with the follow-up on Linux, using the compressed Japanese ROM and isolated save copies. These are physical texture sources in the observed scenes.

| Scene / actor | Baseline blank source | Correct source | Nonzero bytes (of 4,096) |
| --- | --- | --- | ---: |
| South / `0x02C1` | `0x007953D0` | `0x003D13D0` | 4,096 |
| South / `0x02C8` | `0x0078B6E0` | `0x003C76E0` | 3,812 |
| West / `0x02C0` | `0x007A2610` | `0x003DC610` | 4,096 |
| West / `0x02C1` | `0x007A6D50` | `0x003E0D50` | 4,096 |
| West / `0x02C8` | `0x0078F6E0` | `0x003C96E0` | 3,812 |

All four actor records held the corrected operands in West. The sampled expression cycle did not select the changed `0x02C6` operand. The other three switched between the corrected source and their existing valid alternatives. This also explains why the earlier South addresses differed by the loaded executable overlay base, `0x003C4000` in that run.

The authenticated code generation run retained 6,418 relocations. The changed object compiled and linked into a separate candidate executable on top of the robot fix. The exact-site regression and the focused metadata tests passed. A direct visual pass for each clothing color remains open.
