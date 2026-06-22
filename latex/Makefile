LATEXMK ?= latexmk
TARGET ?= main

.PHONY: all clean

all: $(TARGET).pdf

$(TARGET).pdf: $(TARGET).tex references.bib
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error $(TARGET).tex

clean:
	$(LATEXMK) -C $(TARGET).tex
