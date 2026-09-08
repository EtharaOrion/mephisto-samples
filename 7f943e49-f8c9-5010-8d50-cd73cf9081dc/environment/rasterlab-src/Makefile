CC ?= cc
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -fno-fast-math
LDFLAGS ?=

OBJS = rasterlab.o main.o

rasterlab: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS)

rasterlab.o: rasterlab.c rasterlab.h
	$(CC) $(CFLAGS) -c rasterlab.c

main.o: main.c rasterlab.h
	$(CC) $(CFLAGS) -c main.c

clean:
	rm -f rasterlab $(OBJS)

.PHONY: clean
