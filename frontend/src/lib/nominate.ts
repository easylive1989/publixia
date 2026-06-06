// "推薦參戰" — nominate a guru to track. No backend yet, so the buttons open a
// prefilled email to the editor; swap this for a form/endpoint when one exists.
export const nominateHref =
  'mailto:easylive1989@gmail.com' +
  '?subject=' + encodeURIComponent('推薦老師參戰') +
  '&body=' + encodeURIComponent('想推薦的老師（名字 + 平台/Podcast 連結）：\n\n推薦理由（選填）：');
