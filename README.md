# homework-13

Docker-tävling mellan två självförbättrande AI-harnesses (claude och openai).
Varje spår förbättrar sin egen harness på träningsuppgifter. Sedan körs både
seed-harnessen och den bästa harnessen på dolda uppgifter, och lösningarna
rättas mot dolda tester.

```
python3 score_final.py               # lös de dolda uppgifterna och rätta
python3 score_final.py --grade-only  # rätta bara redan sparade lösningar
```

## Slutresultat

![Slutresultat på dolda uppgifter](Inklistrad%20bild.png)

**Vinnare: claude.** Båda best-harnessarna klarade alla 54 dolda tester, utom
openai i en av tre upprepningar (48/54, fel i `next_business_day`). Openai
använde ungefär hälften så många tokens. Evolutionen förbättrade ingen av
seed-harnessarna.
