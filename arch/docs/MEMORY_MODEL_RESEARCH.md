# ATOMIC++ Memory Model Research

**Status:** Draft  
**Goal:** Compare memory-management options and recommend one for Phase 1.

---

## 1. Options Compared

| Model | Safety | Speed | Beginner-friendly | GC pauses? | Reference cycles? | Complexity to implement |
|-------|--------|-------|-------------------|------------|-------------------|------------------------|
| Manual (C-style malloc/free) | Low — programmer must free every allocation | Fastest | Hard — easy to leak or double-free | No | N/A | Medium |
| Reference Counting (ARC) | High — automatic, no dangling pointers | Fast — small per-ref overhead | Easy — feels automatic | No | Yes — cycles leak unless weak refs | Medium |
| Tracing Garbage Collector (Go/Java style) | High — automatic cleanup | Slower — GC pauses possible | Easy — fully automatic | Yes | No | High |
| Ownership / Borrowing (Rust-style) | Highest — compile-time guarantees | Fast — no runtime cost | Hard — borrow checker is steep | No | No | Very High |

---

## 2. Detailed Analysis

### 2.1 Manual Memory Management
The programmer explicitly allocates and frees memory.
- **Pros:** Maximum control, zero runtime overhead, predictable performance.
- **Cons:** Double-free, use-after-free, and memory leaks are common. Hard for beginners.
- **Verdict:** Rejected for Phase 1. Too unsafe for a language targeting new programmers.

### 2.2 Automatic Reference Counting (ARC)
Every value carries a reference count. When the count reaches zero, memory is freed automatically.
- **Pros:** Automatic (programmer never calls `free`), no garbage-collector pauses, deterministic deallocation, easier to learn than ownership.
- **Cons:** Reference cycles (A points to B, B points to A) can leak memory. Slight runtime overhead for incrementing/decrementing counts.
- **Mitigation:** Document cycles; provide `weak` references in Phase 4 if needed.
- **Verdict:** **Selected for Phase 1.** Best balance of safety, simplicity, and predictable speed.

### 2.3 Tracing Garbage Collector
A background thread periodically scans memory and frees unreachable objects.
- **Pros:** Fully automatic, no cycles, easiest for programmers.
- **Cons:** Unpredictable GC pauses — bad for games and real-time apps. Higher memory usage. Complex to implement well.
- **Verdict:** Rejected for Phase 1. GC pauses conflict with the "predictable speed" goal.

### 2.4 Ownership / Borrowing (Rust-style)
The compiler tracks who owns each value at compile time. References are borrowed with strict rules.
- **Pros:** Compile-time memory safety, no runtime overhead, no GC, no cycles.
- **Cons:** Very steep learning curve. Borrow-checker errors confuse beginners. Complex to implement.
- **Verdict:** Rejected for Phase 1. Contradicts the "simple enough for a 10-year-old" goal. Can be reconsidered in Phase 4 as an optional strict mode.

---

## 3. Recommendation

**ATOMIC++ Phase 1 uses ARC (Automatic Reference Counting).**

- Safe by default (no manual `free`, no dangling pointers).
- No GC pauses (important for games).
- Simple mental model: "the language cleans up when you're done."
- Easy to implement on top of a C backend (emit `retain`/`release` calls or use a simple runtime).

**Trade-offs accepted:** Reference cycles can leak. This is documented and mitigated with education (avoid circular references) until weak references are added in a later phase.
