import test from 'node:test';
import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import {MarkdownContent} from '../app/v28/core/markdown-content';

test('draft preview renders headings, lists, emphasis, tables and code',()=>{
 const html=renderToStaticMarkup(<MarkdownContent text={'# 方案\n\n**重点**\n\n- 第一项\n- 第二项\n\n| 阶段 | 状态 |\n| --- | --- |\n| 实施 | 就绪 |\n\n```js\nconst value = 1;\n```'}/>);
 assert.match(html,/<h1>方案<\/h1>/);assert.match(html,/<strong>重点<\/strong>/);assert.match(html,/<ul>/);assert.match(html,/<table>/);assert.match(html,/<pre><code/);assert.doesNotMatch(html,/# 方案/);
});
test('untrusted drafts cannot execute HTML or unsafe links, or fetch remote images',()=>{
 const html=renderToStaticMarkup(<MarkdownContent text={'<script>alert(1)</script>\n\n[点击](javascript:alert%281%29)\n\n![截图](https://example.com/tracker.png)'}/>);
 assert.doesNotMatch(html,/<script|javascript:|<img/);assert.match(html,/noopener noreferrer/);
});
test('search highlights content after parsing without breaking Markdown',()=>{
 const html=renderToStaticMarkup(<MarkdownContent text={'## **项目里程碑**\n\n项目里程碑与时间\n\n`项目里程碑`'} highlight="项目里程碑"/>);
 assert.match(html,/<strong><mark>项目里程碑<\/mark><\/strong>/);assert.match(html,/<mark>项目里程碑<\/mark>与时间/);assert.match(html,/<code>项目里程碑<\/code>/);
});
