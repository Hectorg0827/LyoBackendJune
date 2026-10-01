# Evals

Checks that need a real model, and so cannot live in the test suite.

`pytest` must pass on a laptop with no API key. Anything whose answer depends
on what a model actually says therefore cannot be a test — mocking the model
turns it into a test of the mock. These are run deliberately instead:

```
python -m evals.classifier_new_test
```

Exit code is non-zero when any case is wrong, so CI can run them on a job that
does have keys.

## What is here

**`classifier_new_test`** — does `describes_a_different_test` recognise a
second exam? This is the decision behind "I also have a social studies test"
either starting a new intake or being answered with the plan the learner
already has, which was the reported bug. A wrong *yes* invents an exam nobody
sits and interrogates the learner about it; a wrong *no* is the bug itself.
The cases include the reported phrasings verbatim, typos and all.

Read the two directions separately in the output. They are not equally bad.

## Running with no provider configured

Every case comes back `False`, because the classifier fails closed. That is
the intended behaviour and it is also worth seeing: it is what a learner gets
when the provider is down, which is why the classifier distinguishes "no"
from "could not ask" and the reply says which happened.
