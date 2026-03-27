const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat, TableOfContents,
  PageBreak
} = require('docx');
const fs = require('fs');

// ===== 样式常量 =====
const BLUE_HEADER = "1F497D";
const LIGHT_BLUE = "D6E4F0";
const LIGHT_GRAY = "F2F2F2";
const BORDER = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const CELL_BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };

function h(text, level) {
  return new Paragraph({ heading: level, children: [new TextRun(text)] });
}

function p(children, opts = {}) {
  if (typeof children === 'string') children = [new TextRun(children)];
  return new Paragraph({ children, ...opts });
}

function bold(text, size) {
  return new TextRun({ text, bold: true, ...(size ? { size } : {}) });
}

function note(text) {
  return new Paragraph({
    indent: { left: 360 },
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text: "⚠ " + text, color: "C0392B", bold: true, size: 20 })]
  });
}

function info(text) {
  return new Paragraph({
    indent: { left: 360 },
    spacing: { before: 60, after: 60 },
    children: [new TextRun({ text: "ℹ " + text, color: "1A5276", size: 20 })]
  });
}

function bullet(text, ref = "bl") {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: typeof text === 'string' ? [new TextRun(text)] : text
  });
}

function numbered(text, ref) {
  return new Paragraph({
    numbering: { reference: ref, level: 0 },
    children: typeof text === 'string' ? [new TextRun(text)] : text
  });
}

function pvRow(pv, desc, type, rw) {
  const hdr = { fill: LIGHT_BLUE, type: ShadingType.CLEAR };
  const mk = (txt, bd = false) => new Paragraph({ children: [new TextRun({ text: txt, bold: bd, size: 18 })] });
  return new TableRow({ children: [
    new TableCell({ borders: CELL_BORDERS, width: { size: 3600, type: WidthType.DXA }, children: [mk(pv, true)] }),
    new TableCell({ borders: CELL_BORDERS, width: { size: 3200, type: WidthType.DXA }, children: [mk(desc)] }),
    new TableCell({ borders: CELL_BORDERS, width: { size: 1000, type: WidthType.DXA }, children: [mk(type)] }),
    new TableCell({ borders: CELL_BORDERS, width: { size: 1560, type: WidthType.DXA }, children: [mk(rw)] }),
  ]});
}

function pvHdrRow() {
  const mk = (txt) => new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: txt, bold: true, size: 20, color: "FFFFFF" })] });
  const cell = (txt, w) => new TableCell({ borders: CELL_BORDERS, width: { size: w, type: WidthType.DXA }, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, children: [mk(txt)] });
  return new TableRow({ tableHeader: true, children: [
    cell("PV 名称", 3600), cell("说明", 3200), cell("类型", 1000), cell("读/写", 1560)
  ]});
}

function stateRow(state, code, desc, action) {
  const mk = (txt, bd = false, color) => new Paragraph({ children: [new TextRun({ text: txt, bold: bd, size: 18, ...(color ? { color } : {}) })] });
  return new TableRow({ children: [
    new TableCell({ borders: CELL_BORDERS, width: { size: 2200, type: WidthType.DXA }, children: [mk(state, true)] }),
    new TableCell({ borders: CELL_BORDERS, width: { size: 900, type: WidthType.DXA }, children: [mk(code, false, "7F8C8D")] }),
    new TableCell({ borders: CELL_BORDERS, width: { size: 3300, type: WidthType.DXA }, children: [mk(desc)] }),
    new TableCell({ borders: CELL_BORDERS, width: { size: 2960, type: WidthType.DXA }, children: [mk(action)] }),
  ]});
}

function stateHdrRow() {
  const mk = (txt) => new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: txt, bold: true, size: 20, color: "FFFFFF" })] });
  const cell = (txt, w) => new TableCell({ borders: CELL_BORDERS, width: { size: w, type: WidthType.DXA }, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, children: [mk(txt)] });
  return new TableRow({ tableHeader: true, children: [
    cell("状态", 2200), cell("代码", 900), cell("含义", 3300), cell("操作员动作", 2960)
  ]});
}

// ===== 正文内容 =====

const doc = new Document({
  numbering: {
    config: [
      { reference: "bl", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "step1", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "step2", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "step3", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "step4", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "step5", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal",
        run: { size: 64, bold: true, color: BLUE_HEADER, font: "Arial" },
        paragraph: { spacing: { before: 480, after: 240 }, alignment: AlignmentType.CENTER } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, color: BLUE_HEADER, font: "Arial" },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: "BDC3C7" } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, color: "2C3E50", font: "Arial" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "566573", font: "Arial" },
        paragraph: { spacing: { before: 180, after: 60 }, outlineLevel: 2 } },
    ]
  },
  sections: [{
    properties: { page: { margin: { top: 1440, right: 1260, bottom: 1440, left: 1260 } } },
    headers: {
      default: new Header({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        border: { bottom: { style: BorderStyle.SINGLE, size: 1, color: "BDC3C7" } },
        spacing: { after: 120 },
        children: [new TextRun({ text: "RFQ 自动老练系统 — 操作说明", color: "7F8C8D", size: 18 })]
      })] })
    },
    footers: {
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        border: { top: { style: BorderStyle.SINGLE, size: 1, color: "BDC3C7" } },
        children: [
          new TextRun({ text: "第 ", size: 18, color: "7F8C8D" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "7F8C8D" }),
          new TextRun({ text: " 页", size: 18, color: "7F8C8D" })
        ]
      })] })
    },
    children: [

      // ===== 封面 =====
      new Paragraph({ heading: HeadingLevel.TITLE, spacing: { before: 1440 }, children: [new TextRun("RFQ 自动老练系统")] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: "操 作 说 明", size: 40, color: "566573" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600, after: 120 }, children: [new TextRun({ text: "版本 3.0", size: 22, color: "7F8C8D" })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: "2025-11", size: 22, color: "7F8C8D" })] }),
      new Paragraph({ children: [new PageBreak()] }),

      // ===== 目录 =====
      new TableOfContents("目  录", { hyperlink: true, headingStyleRange: "1-3" }),
      new Paragraph({ children: [new PageBreak()] }),

      // ===== 1. 系统概述 =====
      h("1  系统概述", HeadingLevel.HEADING_1),
      p("RFQ 自动老练程序通过 EPICS Channel Access 与硬件通信，自动完成射频腔的功率爬升与脉宽展宽过程，无需人工逐步调节 Drive。"),
      p([]),
      h("主要功能", HeadingLevel.HEADING_2),
      bullet("自动调节 RF Drive，使腔体功率收敛至目标值"),
      bullet("在脉冲模式下，功率达标后自动展宽脉冲宽度"),
      bullet("支持多个功率目标依次完成，实现分阶段老练"),
      bullet("实时监测真空，超标时自动暂停并等待恢复"),
      bullet("故障自动复位，超过最大次数后停机报警"),
      bullet("支持运行中暂停、参数热修改、恢复继续"),
      p([]),

      h("老练流程简图", HeadingLevel.HEADING_2),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        children: [new TextRun({ text: "启动  →  初始化（打开RF）  →  调节功率  →  展宽脉冲  →  切换到下一功率目标（循环）  →  完成", font: "Courier New", size: 20 })]
      }),
      p([]),

      // ===== 2. 启动前准备 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("2  启动前准备", HeadingLevel.HEADING_1),

      h("2.1  检查硬件状态", HeadingLevel.HEADING_2),
      numbered("确认 RF 系统处于可操作状态，无残留故障", "step1"),
      numbered("确认所有真空计读数正常（< 5×10⁻⁵ Pa）", "step1"),
      numbered("确认 EPICS IOC 正常运行，可读取各 PV", "step1"),
      p([]),

      h("2.2  配置 config.yaml", HeadingLevel.HEADING_2),
      p("config.yaml 位于程序根目录，启动前按需修改以下参数："),
      p([]),

      h("功率目标列表（多目标模式）", HeadingLevel.HEADING_3),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        children: [new TextRun({ text: "power_targets: [16, 17, 18, 22]   # 单位 kW，依次递增", font: "Courier New", size: 20, color: "1A5276" })]
      }),
      p('程序会按列表顺序，对每个功率目标完成一轮"调功率->展脉宽"，全部完成后报告老练结束。'),
      info("若设置为空列表 power_targets: []，则退回单目标模式，从 AutoC_TargetPower PV 读取目标值。"),
      p([]),

      h("真空阈值", HeadingLevel.HEADING_3),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        children: [new TextRun({ text: "vacuum:", font: "Courier New", size: 20, color: "1A5276" })]
      }),
      new Paragraph({
        indent: { left: 720 },
        children: [new TextRun({ text: "  threshold: 5.0e-5   # 单位 Pa", font: "Courier New", size: 20, color: "1A5276" })]
      }),
      p("任意真空计超过此值，系统进入 WAITING_VACUUM 状态暂停老练，等待真空恢复后自动继续。"),
      p([]),

      h("最大故障次数", HeadingLevel.HEADING_3),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        children: [new TextRun({ text: "loop:", font: "Courier New", size: 20, color: "1A5276" })]
      }),
      new Paragraph({
        indent: { left: 720 },
        children: [new TextRun({ text: "  max_faults: 20      # 超过后进入 ERROR 状态", font: "Courier New", size: 20, color: "1A5276" })]
      }),
      p([]),

      h("2.3  通过 PV 设置运行参数", HeadingLevel.HEADING_2),
      p("以下参数在启动前通过 EPICS PV 设置（可使用控制界面或 caput 命令）："),
      p([]),

      new Table({
        columnWidths: [3600, 2400, 1680, 1680],
        margins: { top: 80, bottom: 80, left: 160, right: 160 },
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 3600, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "PV 名称", bold: true, size: 20, color: "FFFFFF" })] })] }),
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 2400, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "说明", bold: true, size: 20, color: "FFFFFF" })] })] }),
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 1680, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "典型值", bold: true, size: 20, color: "FFFFFF" })] })] }),
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 1680, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "单位", bold: true, size: 20, color: "FFFFFF" })] })] }),
          ]}),
          ...[
            ["AutoC_InitDrive", "RF 启动时的初始 Drive", "100", "—"],
            ["AutoC_PulseStart", "脉冲模式起始脉宽", "100", "ms"],
            ["AutoC_PulseEnd", "脉冲模式目标脉宽", "1000", "ms"],
            ["AutoC_PulseStep", "每步展宽量", "50", "ms"],
            ["AutoC_DriveStep1", "功率调节大步长（误差大时）", "10", "—"],
            ["AutoC_DriveStep2", "功率调节小步长（误差小时）", "2", "—"],
            ["AutoC_MarginLarge", "大步长/小步长切换阈值", "5", "kW"],
            ["AutoC_MarginSmall", "功率达标判据", "1", "kW"],
            ["WaitTime_Set", "每步展脉宽前稳定等待时间", "60", "s"],
          ].map(([pv, desc, val, unit]) => new TableRow({ children: [
            new TableCell({ borders: CELL_BORDERS, width: { size: 3600, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: pv, font: "Courier New", size: 18 })] })] }),
            new TableCell({ borders: CELL_BORDERS, width: { size: 2400, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: desc, size: 18 })] })] }),
            new TableCell({ borders: CELL_BORDERS, width: { size: 1680, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: val, size: 18 })] })] }),
            new TableCell({ borders: CELL_BORDERS, width: { size: 1680, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: unit, size: 18 })] })] }),
          ]}))
        ]
      }),
      p([]),

      // ===== 3. 启动程序 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("3  启动程序", HeadingLevel.HEADING_1),

      h("3.1  启动命令", HeadingLevel.HEADING_2),
      p("在程序根目录下执行："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "python main.py", font: "Courier New", size: 22, bold: true })]
      }),
      p("程序启动后进入 IDLE 状态，等待启动信号。"),
      p([]),

      h("3.2  启动老练", HeadingLevel.HEADING_2),
      p("程序运行后，通过 EPICS 发送启动信号："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "caput RFQ:LLRF:Con01:AutoC_Start 1", font: "Courier New", size: 20 })]
      }),
      p("系统收到信号后立即进入初始化流程："),
      numbered("从 PV 读取参数（功率目标、脉宽参数等）", "step2"),
      numbered("识别 RF 模式（脉冲 / CW）", "step2"),
      numbered("打开 RF，设置初始 Drive，打开频率扫描与跟踪", "step2"),
      numbered("RF 启动成功后进入功率调节状态", "step2"),
      p([]),
      note("RF 启动最多重试 3 次，每次间隔 2 秒。全部失败则进入 ERROR 状态。"),
      p([]),

      // ===== 4. 状态说明 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("4  系统状态说明", HeadingLevel.HEADING_1),
      p("当前状态通过 AutoC_Status PV 实时更新，可在控制界面监视。"),
      p([]),

      new Table({
        columnWidths: [2200, 900, 3300, 2960],
        margins: { top: 80, bottom: 80, left: 160, right: 160 },
        rows: [
          stateHdrRow(),
          stateRow("IDLE", "#0", "空闲，等待启动信号", "设置参数后发 AutoC_Start=1"),
          stateRow("INITIALIZING", "#10", "正在启动 RF 系统", "等待完成，无需干预"),
          stateRow("ADJUSTING_POWER", "#20", "正在调节 RF Drive，使功率收敛到目标值", "监视功率变化，无需干预"),
          stateRow("EXPANDING_PULSE", "#30", "功率达标，正在按步骤展宽脉冲", "监视脉宽变化，无需干预"),
          stateRow("WAITING_VACUUM", "#25", "真空超标，已暂停，等待真空恢复", "检查真空系统，真空恢复后自动继续"),
          stateRow("PAUSED", "#15", "用户暂停，RF 保持运行", "修改参数后发 AutoC_Start=1 恢复"),
          stateRow("COMPLETED", "#90", "所有功率目标已完成，老练结束", "记录数据，发 AutoC_Reset=1 复位"),
          stateRow("ERROR", "#100", "超过最大故障次数或系统异常", "排查故障后发 AutoC_Reset=1 复位"),
          stateRow("STOPPED", "#101", "用户停止或程序中断", "发 AutoC_Reset=1 复位后可重新启动"),
        ]
      }),
      p([]),

      // ===== 5. 多目标功率老练 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("5  多目标功率老练", HeadingLevel.HEADING_1),

      h("5.1  工作原理", HeadingLevel.HEADING_2),
      p("在 config.yaml 中设置 power_targets 列表后，系统按以下流程循环执行："),
      p([]),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        children: [new TextRun({ text: "对每个功率目标 Tᵢ：", bold: true, size: 22 })]
      }),
      bullet([bold("① "), new TextRun("调节 Drive → 使功率收敛到 Tᵢ（在当前脉宽下）")]),
      bullet([bold("② "), new TextRun("功率达标后，开始按步长展宽脉冲（PulseStart → PulseEnd）")]),
      bullet([bold("③ "), new TextRun("每步展脉宽前等待 WaitTime_Set 秒")]),
      bullet([bold("④ "), new TextRun("脉宽达到 PulseEnd 后，切换到 Tᵢ₊₁，脉宽重置到 PulseStart")]),
      bullet([bold("⑤ "), new TextRun("最后一个目标的脉宽完成后，系统进入 COMPLETED")]),
      p([]),

      h("5.2  示例配置", HeadingLevel.HEADING_2),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 60 },
        children: [new TextRun({ text: "# config.yaml", font: "Courier New", size: 20, color: "7F8C8D" })]
      }),
      new Paragraph({ indent: { left: 720 }, children: [new TextRun({ text: "power_targets: [16, 17, 18, 22]", font: "Courier New", size: 20, color: "1A5276" })] }),
      p([]),
      new Paragraph({ indent: { left: 720 }, children: [new TextRun({ text: "# PV 设置", font: "Courier New", size: 20, color: "7F8C8D" })] }),
      new Paragraph({ indent: { left: 720 }, children: [new TextRun({ text: "AutoC_PulseStart = 100  ms", font: "Courier New", size: 20, color: "1A5276" })] }),
      new Paragraph({ indent: { left: 720 }, children: [new TextRun({ text: "AutoC_PulseEnd   = 1000 ms", font: "Courier New", size: 20, color: "1A5276" })] }),
      p([]),
      p("程序将依次执行：16kW×(100→1000ms)，17kW×(100→1000ms)，18kW×(100→1000ms)，22kW×(100→1000ms)，共四轮展脉宽后完成。"),
      p([]),

      // ===== 6. 暂停与恢复 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("6  暂停、恢复与停止", HeadingLevel.HEADING_1),

      h("6.1  暂停", HeadingLevel.HEADING_2),
      p("在老练运行中（ADJUSTING_POWER / EXPANDING_PULSE / WAITING_VACUUM），将 Start 置 0 即可暂停："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "caput RFQ:LLRF:Con01:AutoC_Start 0", font: "Courier New", size: 20 })]
      }),
      p("暂停时 RF 保持运行，功率和脉宽维持当前值，系统进入 PAUSED 状态等待指令。"),
      p([]),

      h("6.2  修改参数（热更新）", HeadingLevel.HEADING_2),
      p("在 PAUSED 状态下，可修改以下内容，恢复时自动生效："),
      bullet("通过 PV 修改：功率步长、裕度、等待时间等控制 PV"),
      bullet("通过 config.yaml 修改：power_targets 列表、真空阈值等"),
      note("config.yaml 修改后必须通过暂停/恢复触发重新读取，程序不会自动检测文件变化。"),
      p([]),

      h("6.3  恢复运行", HeadingLevel.HEADING_2),
      p("修改完成后，将 Start 置 1 恢复："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "caput RFQ:LLRF:Con01:AutoC_Start 1", font: "Courier New", size: 20 })]
      }),
      p("系统重新加载所有参数（包括 config.yaml），然后从暂停前的状态继续执行。"),
      p([]),

      h("6.4  中途修改功率目标列表", HeadingLevel.HEADING_2),
      numbered("发送 AutoC_Start=0，等待进入 PAUSED 状态", "step3"),
      numbered("修改 config.yaml 中的 power_targets 列表", "step3"),
      numbered("发送 AutoC_Start=1，系统重新加载列表并继续", "step3"),
      p([]),
      info("若修改后列表长度缩短，且当前目标索引已超出，系统自动从第一个目标重新开始。"),
      p([]),

      h("6.5  完全停止", HeadingLevel.HEADING_2),
      p("在 IDLE 状态下发送 Start=0，系统进入 STOPPED 状态，RF 关闭："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "# 先暂停（若正在运行）", font: "Courier New", size: 20, color: "7F8C8D" })]
      }),
      new Paragraph({ indent: { left: 720 }, shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR }, children: [new TextRun({ text: "caput RFQ:LLRF:Con01:AutoC_Start 0", font: "Courier New", size: 20 })] }),
      new Paragraph({ indent: { left: 720 }, shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR }, children: [new TextRun({ text: "# 等待进入 PAUSED，再次置 0 停止", font: "Courier New", size: 20, color: "7F8C8D" })] }),
      new Paragraph({ indent: { left: 720 }, shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR }, spacing: { after: 120 }, children: [new TextRun({ text: "caput RFQ:LLRF:Con01:AutoC_Start 0", font: "Courier New", size: 20 })] }),
      p([]),

      // ===== 7. 故障处理 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("7  故障处理", HeadingLevel.HEADING_1),

      h("7.1  自动故障处理", HeadingLevel.HEADING_2),
      p("程序通过 EPICS 回调实时监听以下故障信号，无需人工干预："),
      p([]),

      new Table({
        columnWidths: [2400, 2400, 4560],
        margins: { top: 80, bottom: 80, left: 160, right: 160 },
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 2400, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "故障类型", bold: true, size: 20, color: "FFFFFF" })] })] }),
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 2400, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "监测 PV", bold: true, size: 20, color: "FFFFFF" })] })] }),
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 4560, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "自动响应", bold: true, size: 20, color: "FFFFFF" })] })] }),
          ]}),
          ...([
            ["弧光（Arc）", "ArcStatus_Rd", "故障计数+1，执行联锁复位序列，等待状态机重新初始化"],
            ["真空联锁（VacInterlock）", "InterlockStatus_Rd", "优先发真空复位，随后执行联锁复位和功率故障复位"],
            ["SSA 前向功率", "ForwardPowerComp", "故障计数+1，执行功率故障复位"],
            ["反射功率", "ReflectedPowerComp", "故障计数+1，执行功率故障复位"],
          ].map(([type, pv, resp]) => new TableRow({ children: [
            new TableCell({ borders: CELL_BORDERS, width: { size: 2400, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: type, size: 18, bold: true })] })] }),
            new TableCell({ borders: CELL_BORDERS, width: { size: 2400, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: pv, font: "Courier New", size: 18 })] })] }),
            new TableCell({ borders: CELL_BORDERS, width: { size: 4560, type: WidthType.DXA }, children: [new Paragraph({ children: [new TextRun({ text: resp, size: 18 })] })] }),
          ]})))
        ]
      }),
      p([]),

      h("7.2  故障计数与超限", HeadingLevel.HEADING_2),
      p([bold("故障累计次数"), new TextRun(" 可在日志中查看。达到 config.yaml 中 max_faults 设定值（默认 20 次）后，系统进入 ERROR 状态，RF 自动关闭，程序停止调节。")]),
      p([]),
      note("进入 ERROR 后程序不会自动重启，必须由操作员排查原因后手动复位。"),
      p([]),

      h("7.3  手动复位", HeadingLevel.HEADING_2),
      p("在 ERROR 或 COMPLETED 状态下，发送 Reset 信号清零所有计数并返回 IDLE："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "caput RFQ:LLRF:Con01:AutoC_Reset 1", font: "Courier New", size: 20 })]
      }),
      p("复位后可重新设置参数并再次启动。"),
      p([]),

      // ===== 8. 真空监控 =====
      h("8  真空监控", HeadingLevel.HEADING_1),
      p("程序持续监测以下 8 个真空计（通过 EPICS 回调）："),
      p([]),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 80, after: 80 },
        children: [new TextRun({ text: "RFQ:Vac1 ~ RFQ:Vac8", font: "Courier New", size: 20 })]
      }),
      p([]),
      p("任意一个真空计的读数超过阈值（默认 5×10⁻⁵ Pa）时："),
      numbered("系统记录超标的 PV 名称和数值到日志", "step4"),
      numbered("立即暂停功率调节和脉宽展宽（进入 WAITING_VACUUM）", "step4"),
      numbered("RF 保持运行，功率和脉宽维持当前值", "step4"),
      numbered("持续轮询真空，待所有真空计恢复正常后自动继续", "step4"),
      p([]),
      info("真空阈值可在 config.yaml 中修改（vacuum.threshold），修改后需重启程序生效。"),
      p([]),

      // ===== 9. 老练完成 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("9  老练完成", HeadingLevel.HEADING_1),

      h("9.1  正常完成", HeadingLevel.HEADING_2),
      p("所有功率目标的脉宽均达到 PulseEnd 后，系统进入 COMPLETED 状态："),
      bullet("AutoC_Start PV 自动置 0"),
      bullet("日志记录总故障次数和总迭代次数"),
      bullet("RF 继续运行（Drive 保持在最终值），不自动关闭"),
      p([]),
      note("老练完成后 RF 不会自动关闭，操作员需根据需要手动关闭 RF。"),
      p([]),

      h("9.2  完成后操作", HeadingLevel.HEADING_2),
      numbered("查阅日志文件 rfq_auto_conditioning.log，记录总故障次数", "step5"),
      numbered("根据需要手动关闭 RF（操作 RF 控制界面）", "step5"),
      numbered("发送 AutoC_Reset=1 复位程序，为下次老练做准备", "step5"),
      p([]),

      // ===== 10. 异常情况 =====
      h("10  异常情况处理", HeadingLevel.HEADING_1),

      h("程序无响应 / AutoC_Start 读取失败", HeadingLevel.HEADING_2),
      bullet("检查 EPICS IOC 是否正常运行"),
      bullet("检查网络连接，确认 UDP 5064/5065 端口畅通"),
      bullet("检查 EPICS_CA_ADDR_LIST 环境变量是否正确设置"),
      p([]),

      h("RF 启动后功率长时间不收敛", HeadingLevel.HEADING_2),
      bullet("检查 AutoC_InitDrive 设置是否合理"),
      bullet("检查功率调节步长（DriveStep1/DriveStep2）和裕度（MarginLarge/MarginSmall）"),
      bullet("查看日志确认是否有频繁故障打断调节过程"),
      p([]),

      h("频繁弧光故障", HeadingLevel.HEADING_2),
      bullet("减小功率目标或增大步进间隔（WaitTime_Set）"),
      bullet("检查腔体状态"),
      bullet("若故障次数未超限，程序会自动处理；若超限，需排查后手动复位"),
      p([]),

      h("真空持续超标", HeadingLevel.HEADING_2),
      bullet("系统将一直保持 WAITING_VACUUM 状态，不会自动停机"),
      bullet("需要停机时发送 AutoC_Start=0 暂停，再发 AutoC_Reset=1 停止"),
      p([]),

      // ===== 11. 日志 =====
      h("11  日志文件", HeadingLevel.HEADING_1),
      p("日志文件默认路径："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "rfq_auto_conditioning.log", font: "Courier New", size: 20 })]
      }),
      p("日志记录内容包括：状态转换、功率调节过程、故障事件、真空异常、参数读取结果等。"),
      p("日志级别默认为 INFO，如需更详细的调试信息可在 config.yaml 中设置为 DEBUG："),
      new Paragraph({
        indent: { left: 720 },
        spacing: { before: 120, after: 120 },
        shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR },
        children: [new TextRun({ text: "logging:", font: "Courier New", size: 20, color: "1A5276" })]
      }),
      new Paragraph({ indent: { left: 720 }, shading: { fill: LIGHT_GRAY, type: ShadingType.CLEAR }, spacing: { after: 120 }, children: [new TextRun({ text: "  level: 'DEBUG'", font: "Courier New", size: 20, color: "1A5276" })] }),
      p([]),

      // ===== 12. 快速参考 =====
      new Paragraph({ children: [new PageBreak()] }),
      h("12  快速操作参考", HeadingLevel.HEADING_1),
      p([]),

      new Table({
        columnWidths: [3000, 6360],
        margins: { top: 80, bottom: 80, left: 160, right: 160 },
        rows: [
          new TableRow({ tableHeader: true, children: [
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 3000, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "操作", bold: true, size: 20, color: "FFFFFF" })] })] }),
            new TableCell({ borders: CELL_BORDERS, shading: { fill: BLUE_HEADER, type: ShadingType.CLEAR }, width: { size: 6360, type: WidthType.DXA }, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "命令", bold: true, size: 20, color: "FFFFFF" })] })] }),
          ]}),
          ...[
            ["启动老练", "caput RFQ:LLRF:Con01:AutoC_Start 1"],
            ["暂停", "caput RFQ:LLRF:Con01:AutoC_Start 0"],
            ["恢复", "caput RFQ:LLRF:Con01:AutoC_Start 1"],
            ["复位（回 IDLE）", "caput RFQ:LLRF:Con01:AutoC_Reset 1"],
            ["查看当前状态", "caput RFQ:LLRF:Con01:AutoC_Status"],
            ["查看当前功率目标", "caget RFQ:LLRF:Con01:AutoC_TargetPower"],
            ["查看腔体功率", "caget RFQ:LLRF:Con01_RFIn03:Power"],
            ["查看当前脉宽", "caget RFQ:LLRF:Con01:RFPulseOnTime_Set"],
            ["监视功率变化", "camonitor RFQ:LLRF:Con01_RFIn03:Power"],
          ].map(([op, cmd], i) => new TableRow({
            children: [
              new TableCell({ borders: CELL_BORDERS, width: { size: 3000, type: WidthType.DXA }, shading: { fill: i % 2 === 0 ? "FFFFFF" : LIGHT_GRAY, type: ShadingType.CLEAR }, children: [new Paragraph({ children: [new TextRun({ text: op, bold: true, size: 20 })] })] }),
              new TableCell({ borders: CELL_BORDERS, width: { size: 6360, type: WidthType.DXA }, shading: { fill: i % 2 === 0 ? "FFFFFF" : LIGHT_GRAY, type: ShadingType.CLEAR }, children: [new Paragraph({ children: [new TextRun({ text: cmd, font: "Courier New", size: 18 })] })] }),
            ]
          }))
        ]
      }),

    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("E:/OneDrive/200-Academic/03-Project/西核所/AutoConditioning/docs/操作说明.docx", buf);
  console.log("✓ 操作说明.docx 已生成");
});
