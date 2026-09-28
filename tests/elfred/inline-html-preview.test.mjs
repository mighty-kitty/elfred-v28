import test from 'node:test';
import assert from 'node:assert/strict';
import {extractHtmlPreview} from '../../app/v28/core/inline-html-preview.mjs';

test('HTML 代码块可直接预览，说明文字与代码分别保留',()=>{
 const result=extractHtmlPreview('这是一个按钮。\n\n```html\n<button onclick="this.textContent=\'完成\'">开始</button>\n```\n\n可以点击。');
 assert.match(result.html,/<button/);
 assert.equal(result.description,'这是一个按钮。\n\n可以点击。');
});

test('完整 HTML 文档可预览，普通代码与普通社区文字不误判',()=>{
 assert.match(extractHtmlPreview('<!doctype html><html><body>你好</body></html>').html,/<body>你好/);
 assert.match(extractHtmlPreview('<div>卡片</div>').html,/<div>卡片/);
 assert.equal(extractHtmlPreview('```js\nconsole.log(1)\n```'),null);
 assert.equal(extractHtmlPreview('这是一段介绍 <button> 标签的文字。'),null);
 assert.equal(extractHtmlPreview('```html\n'+'x'.repeat(80001)+'\n```'),null);
});

test('分开的 HTML、CSS 和 JavaScript 代码块合成同一隔离网页',()=>{
 const result=extractHtmlPreview('说明\n\n```html\n<button id="test">点我</button>\n```\n```css\nbutton{color:red}\n```\n```js\ndocument.getElementById("test").textContent="已运行"\n```');
 assert.match(result.html,/<style>button\{color:red\}<\/style>/);
 assert.match(result.html,/<script>document\.getElementById/);
 assert.equal(result.description,'说明');
 assert.match(result.code,/```css/);
});
