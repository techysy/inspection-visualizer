# Bootstrap 5 自定义模态框点击无响应：一个 `pointer-events: none` 引发的排查

## 项目背景

在一个巡检数据可视化项目中，我用纯 CSS + 原生 JavaScript 实现了一个自定义模态框（Modal），用于编辑仪表盘类型配置。没有使用 Bootstrap 自带的 Modal 组件，因为需要更灵活的样式控制。

模态框结构很简单：

```html
<!-- 自定义模态框遮罩层 -->
<div id="type-modal" class="modal-mask" style="display:none">
    <!-- 模态框内容 -->
    <div id="type-modal-dialog" class="modal-dialog">
        <h5>编辑仪表盘类型</h5>
        <!-- 表单内容... -->
        <div class="d-flex gap-2">
            <button class="btn btn-primary flex-fill" id="modal-confirm">保存</button>
            <button class="btn btn-outline-secondary" id="modal-cancel">取消</button>
        </div>
    </div>
</div>
```

自定义的 CSS 样式：

```css
.modal-mask {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    padding: 1rem;
}

.modal-dialog {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    width: 100%;
    max-width: 500px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    position: relative;
}
```

JavaScript 事件绑定也完全正常：

```javascript
document.getElementById('modal-confirm').addEventListener('click', async () => {
    // 保存逻辑...
});
```

## 问题现象

点击模态框中的「保存」按钮，**完全没有任何反应**：

- 没有触发 `click` 事件
- 网络面板中没有发出任何请求
- 控制台也没有报错
- 模态框内的所有按钮（保存、取消）都像被"冻住"了一样

但模态框本身**可以正常打开和关闭**（通过点击遮罩层），说明事件监听器本身是绑定了的。

## 排查过程

### 第一步：怀疑是 JavaScript 事件绑定问题

最初我以为是事件监听器没有正确绑定到按钮上。检查了代码结构：

```javascript
(function() {
    // ... 各种 DOM 操作 ...
    
    document.getElementById('modal-confirm').addEventListener('click', async () => {
        // 保存逻辑
    });
})();
```

IIFE 结构没问题，`getElementById` 能正确找到元素（因为模态框 HTML 在 `<script>` 之前已渲染）。排除。

### 第二步：怀疑是 DOM 元素被覆盖

检查了是否有其他元素覆盖在按钮上方导致点击事件被拦截。查看了 `z-index` 层级关系，发现模态框的 `z-index: 9999` 已经足够高。排除。

### 第三步：尝试在 click handler 中加 try-catch

将整个 click handler 包裹在 `try-catch` 中，发现**handler 根本没有被触发**——这意味着问题不在 handler 内部的逻辑，而是事件根本到达不了按钮。

### 第四步：最终定位到 CSS

仔细检查 Bootstrap 5 的 CSS 源码，发现了关键一行：

```css
/* Bootstrap 5 的 .modal-dialog 默认样式 */
.modal-dialog {
    position: relative;
    width: auto;
    margin: var(--bs-modal-margin);
    pointer-events: none;  /* <-- 就是这行！ */
}
```

**Bootstrap 5 的 `.modal-dialog` 默认设置了 `pointer-events: none`。**

这个设计的本意是：Bootstrap 的 Modal 组件需要外层有 `.modal.show` 类时，才会通过以下规则恢复交互：

```css
.modal.show .modal-dialog {
    pointer-events: auto;
}
```

但我使用的是**自定义的 `.modal-mask`**，而非 Bootstrap 的 `.modal` 类。因此 `.modal.show` 这个选择器永远不会匹配，`pointer-events: none` 一直生效，导致模态框内的**所有元素都无法接收鼠标事件**。

## 解决方案

在自定义的 `.modal-dialog` 样式中添加 `pointer-events: auto`，覆盖 Bootstrap 的默认值：

```css
.modal-dialog {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    width: 100%;
    max-width: 500px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    position: relative;
    pointer-events: auto;  /* 关键修复 */
}
```

一行代码解决问题。

## 根因总结

| 项目 | 说明 |
|------|------|
| **框架** | Bootstrap 5.3.0 |
| **根因** | Bootstrap 的 `.modal-dialog` 默认 `pointer-events: none` |
| **触发条件** | 使用自定义容器替代 Bootstrap 的 `.modal` 类包裹模态框 |
| **影响** | 模态框内所有按钮、输入框、链接均无法点击 |
| **修复** | 在自定义 `.modal-dialog` 样式中添加 `pointer-events: auto` |

## 经验教训

### 1. Bootstrap 的 CSS 不是"透明"的

即使你没有使用 Bootstrap 的 JS 组件，仅引入 CSS 就可能引入隐含的行为约束。`pointer-events: none` 这种属性不会产生任何视觉变化，但会彻底阻止交互，排查成本极高。

### 2. 类名复用有风险

Bootstrap 的 `.modal-dialog` 是一个"有约定"的类名——它假设外层一定是 `.modal`。如果你只复用了类名而没有遵循 Bootstrap 的 DOM 结构约定，就可能踩坑。要么完整遵循 Bootstrap 的组件结构，要么**使用完全不同的类名**避免冲突。

### 3. "无响应"类 Bug 的排查思路

当页面元素点击无响应且无报错时，按以下顺序排查：

1. **`pointer-events`** — 检查元素及所有祖先元素是否被设为 `none`
2. **`z-index` + `position`** — 检查是否有更高层级的元素覆盖
3. **`overflow: hidden`** — 检查元素是否被裁剪出可视区域
4. **`disabled` 属性** — 检查表单元素是否被禁用
5. **事件委托** — 检查事件是否被父元素拦截（如 `stopPropagation`）

可以使用浏览器 DevTools 的 `Event Listeners` 面板查看元素上绑定的事件，用 `Computed` 面板检查 `pointer-events` 的最终计算值。

## 快速验证技巧

如果怀疑是 `pointer-events` 的问题，在 DevTools Console 中执行：

```javascript
// 检查按钮的最终 computed pointer-events
getComputedStyle(document.getElementById('modal-confirm')).pointerEvents
// 如果返回 "none"，就是这个问题
```

或者直接在 DevTools 的 Styles 面板中临时给 `.modal-dialog` 添加 `pointer-events: auto`，看按钮是否立即恢复正常。

---

*本文基于 inspection-visualizer 项目，Bootstrap 5.3.0 环境下的实际排查记录。*
