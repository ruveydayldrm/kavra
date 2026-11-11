import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { isAnswered, QuestionInput, Stem } from "@/components/question-input";
import { Heatmap } from "@/components/viz";
import type { CheckResult, PublicQuestion } from "@/lib/api";
import { I18nProvider } from "@/lib/i18n";
import { messages } from "@/lib/messages";
import { locLabel, splitHighlight } from "@/lib/utils";

const mcq: PublicQuestion = {
  id: 1,
  document_id: 1,
  topic_id: 1,
  topic: "Hücre",
  type: "mcq",
  difficulty: "medium",
  stem: "ATP nerede üretilir?",
  options: ["Mitokondri", "Ribozom", "Golgi", "Lizozom"],
  key_point_count: 0,
};

const wrap = (ui: React.ReactNode) => render(<I18nProvider>{ui}</I18nProvider>);

describe("QuestionInput", () => {
  it("selects an option and reports the index", async () => {
    const onChange = vi.fn();
    wrap(<QuestionInput q={mcq} value={null} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: /Golgi/ }));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("marks correct and wrong choices after grading", () => {
    const result = { correct: false, score: 0, suggested_rating: 1, question: { ...mcq, correct_index: 0 } } as unknown as CheckResult;
    wrap(<QuestionInput q={mcq} value={1} onChange={() => {}} result={result} />);
    const radios = screen.getAllByRole("radio");
    expect(radios[0].className).toContain("border-accent");
    expect(radios[1].className).toContain("bg-danger-soft");
    radios.forEach((r) => expect(r).toBeDisabled());
  });

  it("renders a visible blank for cloze stems", () => {
    wrap(<Stem q={{ ...mcq, type: "cloze", stem: "ATP ____ üretilir." }} />);
    expect(screen.getByLabelText("___")).toBeInTheDocument();
  });
});

describe("isAnswered", () => {
  it("handles every type", () => {
    expect(isAnswered(mcq, null)).toBe(false);
    expect(isAnswered(mcq, 0)).toBe(true);
    expect(isAnswered({ ...mcq, type: "tf" }, false)).toBe(true);
    expect(isAnswered({ ...mcq, type: "open" }, "  ")).toBe(false);
  });
});

describe("utils", () => {
  it("formats locators in both languages", () => {
    expect(locLabel({ kind: "page", page: 3, line_start: 12, line_end: 18 }, messages.tr.loc)).toBe("s. 3 · satır 12–18");
    expect(locLabel({ kind: "time", start: 93, end: 101 }, messages.en.loc)).toBe("1:33 – 1:41");
    expect(locLabel({ kind: "slide", slide: 7 }, messages.en.loc)).toBe("Slide 7");
  });

  it("highlights quotes case-insensitively", () => {
    expect(splitHighlight("Önce A. Sonra İnsülin salgılanır. Bitti.", "insülin salgılanır")).toEqual(["Önce A. Sonra ", "İnsülin salgılanır", ". Bitti."]);
    expect(splitHighlight("abc", "zzz")).toBeNull();
  });
});

describe("Heatmap", () => {
  it("renders one cell per day", () => {
    const days = Array.from({ length: 14 }, (_, i) => ({ date: `2026-11-${String(i + 1).padStart(2, "0")}`, count: i, correct: 0 }));
    const { container } = wrap(<Heatmap days={days} />);
    expect(container.querySelectorAll("[title]").length).toBe(14);
  });
});

describe("messages", () => {
  it("EN has the same keys as TR", () => {
    const keys = (o: object, p = ""): string[] =>
      Object.entries(o).flatMap(([k, v]) => (typeof v === "string" ? [p + k] : keys(v as object, `${p}${k}.`)));
    expect(keys(messages.en).sort()).toEqual(keys(messages.tr).sort());
  });
});
