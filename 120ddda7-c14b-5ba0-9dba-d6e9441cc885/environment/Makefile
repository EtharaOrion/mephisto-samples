# bpfc - starter build.
#
#   make -j4      build ./bpfc
#   make clean    remove objects and the binary
#
# Depends on nothing but a C11 compiler and libc. Do not add -lpcap: linking
# any library outside libc/libm is rejected by the judge.

CC       ?= cc
CPPFLAGS ?= -D_POSIX_C_SOURCE=200809L -Iinclude -Isrc
CFLAGS   ?= -std=c11 -O2 -Wall -Wextra -pedantic
LDFLAGS  ?=
LDLIBS   ?=

BIN  := bpfc
SRC  := src/jsonio.c src/parse.c src/codegen.c src/main.c
OBJ  := $(SRC:.c=.o)
DEP  := $(OBJ:.o=.d)

.PHONY: all clean
all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(OBJ) $(LDLIBS)

%.o: %.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c -o $@ $<

-include $(DEP)

clean:
	rm -f $(OBJ) $(DEP) $(BIN)
