// 응답 문장 표시용: HTML 을 모두 이스케이프한 뒤 **굵게** 만 <strong> 으로 바꾼다 (LLM 문장의 마크다운 대응)
export function formatMessage(text: string): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
  return escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
}
