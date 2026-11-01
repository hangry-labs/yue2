# ASR lyric fidelity

Run `20261101T170052Z-846682fc`, revision `bbc19f2-dirty`, NVIDIA GeForce RTX 5070 Ti. Image `sha256:2c8ed04ae8f7960b8bf46b57c06d9017fbcefde66f8f43f79731b1db9eabb53d`. Isolated inference worker; desktop activity may share the device.

Judge: `Qwen/Qwen3-ASR-0.6B-hf`, full music mix converted to mono 16 kHz. Expected lyrics are never supplied to ASR as a prompt. Unicode NFKC/case normalization preserves accents; punctuation is ignored. WER/CER count insertions, substitutions and deletions and may exceed 100%. Lyric accuracy = max(0, 1 − WER) × 100 for space-delimited languages and CER for Chinese. The ASR judge is imperfect on music, and an expected acceptance range has not been calibrated. Scores are reference observations for matched regression review; no absolute score produces a warning. Spanish/German are experimental model coverage.

| Language | Judged | Mean WER | Mean CER | Median ASR match % | Minimum % | Identical repeat groups |
| --- | --- | --- | --- | --- | --- | --- |
| en | 10/10 | 0.042 | 0.049 | 94.74 | 89.47 | 1/1 |
| zh | 10/10 | n/a | 0.286 | 82.14 | 35.71 | 1/1 |
| es | 10/10 | 0.305 | 0.254 | 70.00 | 40.00 | 1/1 |
| de | 10/10 | 0.135 | 0.073 | 85.00 | 75.00 | 1/1 |

## Transcripts

**measured-00-sunlight-en, seed 91001**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing today.

**measured-01-morning-zh, seed 92001**

阳光照进我房间，你的笑容在眼前，牵着你的手向前，一起走到。

**measured-02-morning-es, seed 93001**

Llega la luz del día, tú dos me daré y dame tu mano al andar, vamos los.

**measured-03-morning-de, seed 94001**

Sonne scheint in uns aus, kommen wir gehen heute raus, nehme ich bei der Hand, wir laufen an den Strand.

**measured-04-morning-de, seed 94002**

Sonne scheint in unser Haus, kommen wir gehen heute raus, nimm mich bei der Hand, wir laufen an den Strand.

**measured-05-morning-es, seed 93002**

Llega la luz del día, tú os me da alegría, dame tu mano al andar, vamos los ojos.

**measured-06-morning-zh, seed 92002**

阳光照进我房间，你的笑。

**measured-07-sunlight-en, seed 91002**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing.

**measured-08-sunlight-en, seed 91001**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing today.

**measured-09-morning-zh, seed 92001**

阳光照进我房间，你的笑容在眼前，牵着你的手向前，一起走到。

**measured-10-morning-es, seed 93001**

Llega la luz del día, tú dos me daré y dame tu mano al andar, vamos los.

**measured-11-morning-de, seed 94001**

Sonne scheint in uns aus, kommen wir gehen heute raus, nehme ich bei der Hand, wir laufen an den Strand.

**measured-12-morning-de, seed 94004**

Sonne scheint in unser Haus. Komm wir gehen heute raus. Nimm ich beide Hand. Wir laufen an dem Strand.

**measured-13-morning-es, seed 93004**

Llega la luz del día, tu voz me da alegría, dame tu mano al andar, vamos los dos.

**measured-14-morning-zh, seed 92004**

阳光照进我房间，你的笑容在眼前，牵着你的手向前，一起走到。

**measured-15-sunlight-en, seed 91004**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing.

**measured-16-sunlight-en, seed 91005**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing.

**measured-17-morning-zh, seed 92005**

阳光照进我房间，你的笑容在眼前，牵着你的手向前一起。

**measured-18-morning-es, seed 93005**

Llega la luz del día, tu voz me da alegría, dame tu mando al andar, vamos los dos a cantar.

**measured-19-morning-de, seed 94005**

Sunshine in unser Haus kommen wir gehen heute raus nimm mich bei der Hand wir laufen an den Strand

**measured-20-morning-de, seed 94006**

Mhm mhm mhm Sonne scheint in unser Haus Komm wir gehen heute raus Nimm mich bei der Hand Wir laufen an den Strand

**measured-21-morning-es, seed 93006**

Arena luz del día tu voz mía tu voz me da alegría la mañana dame tu mano andar damos luz dos árboles

**measured-22-morning-zh, seed 92006**

阳光照进我房间，你的笑。

**measured-23-sunlight-en, seed 91006**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing.

**measured-24-sunlight-en, seed 91007**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing today. Sunlight falls.

**measured-25-morning-zh, seed 92007**

阳光照进我房间，你的笑容在眼前，牵着你的手向前，一起。

**measured-26-morning-es, seed 93007**

Llega la luz del día, tu voz me da alegría, dame tu mano landa, vamos Luzú

**measured-27-morning-de, seed 94007**

Sonne scheint in unser Haus. Komm wir gehen heute raus. Nimm mich bei der Hand. Wir laufen.

**measured-28-morning-de, seed 94008**

Sonne scheint in unser Haus. Komm wir gehen heute raus, nimm mich bei der Hand. Wir laufen an den Strand.

**measured-29-morning-es, seed 93008**

Cada luz del día tuvo me da alegría dame tu mano andar vamos los dos a cantar

**measured-30-morning-zh, seed 92008**

阳光照进我房间，你的笑容在眼前，牵着你的手向前，一起。

**measured-31-sunlight-en, seed 91008**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing today.

**measured-32-sunlight-en, seed 91009**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will sing today.

**measured-33-morning-zh, seed 92009**

阳光照进我房间，你的笑容。

**measured-34-morning-es, seed 93009**

Llega la luz del día, tu voz me da alegría, dame tu mano a la

**measured-35-morning-de, seed 94009**

Sonne scheint in unser Haus. Komm wir gehen heute raus. Nimm mich bei der Hand. Wir laufen an den Strand.

**measured-36-morning-de, seed 94010**

Eh, Sonne scheint in unser Haus. Komm wir gehen heute raus. Nimm mich bei der Hand. Wir laufen an.

**measured-37-morning-es, seed 93010**

Llega la luz del día, tu voz me da alegría.

**measured-38-morning-zh, seed 92010**

阳光照进我房间，你的笑容在眼前，牵着你的手向前，一起走到。

**measured-39-sunlight-en, seed 91010**

Sunlight falls across the floor. Your footsteps reach my door. Take my hand and stay. We will see.

