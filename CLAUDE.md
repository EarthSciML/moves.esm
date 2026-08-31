This repo is an implementation of the EPA MOVES/nonroad model https://github.com/USEPA/EPA_MOVES_Model using EarthSciAST (../EarthSciAST; https://earthsciml.github.io/EarthSciAST/) in .esm files.

All model logic should be contained in .esm files. Tests and examples should be in the "tests" and "analysis" sections of .esm files, respectively. All analyses and test should be conducted using the EarthSciAST rust CLI binary, a copy of which should be kept untracked in the root directory of this repo.  A checked-in shell script should be kept up-to-date to run all of the tests.

The .esm files should be authored compositionally, with separate components, subcomponents, and expression templates used liberally and imported by reference into other components to keep the .esm code succint, simple, and human-interpretable. Avoid repeating logic or calculations, instead factor reused pieces into their own files/components/expression templates and import them by reference. Avoid the use of scripts to mechanically generate .esm files, as they often end up producing expressios that are not properly factored or succinct.

We have already created a rust clone of the moves model, it is at ../moves.rs. It is expected that it may be easier to create an EarthSciAST implementation based on ../moves.rs rather than the canonical MOVES/nonroad code.
