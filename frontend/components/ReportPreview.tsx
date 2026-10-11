"use client";
import { useEffect, useRef, useState } from "react";
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  RenderTask,
} from "pdfjs-dist";
import {
  FileText,
  LoaderCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
export default function ReportPreview({
  id,
  token,
  api,
  variantIndex = 0,
}: {
  id: string;
  token: string;
  api: string;
  variantIndex?: number;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null),
    [error, setError] = useState(""),
    [pageNumber, setPageNumber] = useState(1),
    [ready, setReady] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null),
    container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false,
      task: PDFDocumentLoadingTask | undefined;
    const controller = new AbortController();
    setPdf(null);
    setError("");
    setPageNumber(1);
    setReady(false);
    if (!id) return;
    async function load() {
      const [module, response] = await Promise.all([
        import("pdfjs-dist"),
        fetch(
          api + "/api/v1/reports/" + id + "?variant_index=" + variantIndex,
          {
            headers: { Authorization: "Bearer " + token },
            signal: controller.signal,
          },
        ),
      ]);
      if (!response.ok) throw Error("Не удалось загрузить PDF");
      const data = new Uint8Array(await response.arrayBuffer());
      if (cancelled) return;
      module.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.mjs",
        import.meta.url,
      ).toString();
      task = module.getDocument({ data });
      const document = await task.promise;
      if (cancelled) {
        await task.destroy();
        return;
      }
      setPdf(document);
    }
    load().catch((e) => {
      if (!cancelled) setError(String(e));
    });
    return () => {
      cancelled = true;
      controller.abort();
      task?.destroy().catch(() => {});
    };
  }, [id, token, api, variantIndex]);
  useEffect(() => {
    if (!pdf || !canvas.current || !container.current) return;
    let cancelled = false,
      render: RenderTask | undefined;
    setReady(false);
    async function draw() {
      const page = await pdf!.getPage(pageNumber);
      if (cancelled || !canvas.current || !container.current) return;
      const natural = page.getViewport({ scale: 1 }),
        scale = Math.min(
          (container.current.clientWidth - 20) / natural.width,
          (container.current.clientHeight - 16) / natural.height,
        );
      const viewport = page.getViewport({ scale: Math.max(scale, 0.1) }),
        pixelRatio = window.devicePixelRatio || 1,
        element = canvas.current;
      element.width = Math.ceil(viewport.width * pixelRatio);
      element.height = Math.ceil(viewport.height * pixelRatio);
      element.style.width = viewport.width + "px";
      element.style.height = viewport.height + "px";
      render = page.render({
        canvas: element,
        canvasContext: element.getContext("2d")!,
        viewport,
        transform:
          pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
      });
      await render.promise;
      if (!cancelled) setReady(true);
    }
    draw().catch((e) => {
      if (!cancelled) setError(String(e));
    });
    return () => {
      cancelled = true;
      render?.cancel();
    };
  }, [pdf, pageNumber]);
  return (
    <div className="pdf-frame">
      <div className="pdf-canvas-wrap" ref={container}>
        {pdf && (
          <canvas
            aria-label="Предпросмотр PDF-отчёта"
            data-ready={ready}
            ref={canvas}
          />
        )}
        <div className={"pdf-loading " + (pdf && ready ? "hidden" : "")}>
          <span className="preview-empty">
            {id ? (
              <LoaderCircle className="spin" size={23} />
            ) : (
              <FileText size={30} />
            )}
            <span>
              {error ||
                (id ? "Загружаем отчёт…" : "Выберите расчёт для предпросмотра")}
            </span>
          </span>
        </div>
      </div>
      {pdf && (
        <div className="pdf-pager">
          <button
            aria-label="Предыдущая страница PDF"
            className="icon-button"
            disabled={pageNumber === 1}
            onClick={() => setPageNumber(pageNumber - 1)}
          >
            <ChevronLeft size={14} />
          </button>
          <span>
            Страница {pageNumber} / {pdf.numPages}
          </span>
          <button
            aria-label="Следующая страница PDF"
            className="icon-button"
            disabled={pageNumber === pdf.numPages}
            onClick={() => setPageNumber(pageNumber + 1)}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
