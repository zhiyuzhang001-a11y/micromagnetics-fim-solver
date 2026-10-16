"""Evidence-based Chinese hints. Never changes physical parameters or precision."""
RULES=[
 ('output','必需输出未完整落盘','保留已完成计算和外部费用账，检查可用磁盘/权限并选择新目录恢复；输出失败不能视为成功。'),
 ('nonfinite','出现非有限或模长异常','核对单位、初态模长和alpha/gamma；保持物理参数，减半dt做同窗对照。无NaN不能单独证明精度。'),
 ('budget','资源额度或预测不足','保留最后完整checkpoint；显式增加合理资源或降低输出频率后在新目录恢复。这是未完成，不是科学失败。'),
 ('cache','退磁核身份或校验异常','检查几何/边界/版本；使用新cache目录重新生成并校验，不能换用125网格核。'),
 ('OVF','初态导入不符合声明','核对A/B两个文件的OVF2格式、单位、尺寸/原点和解释方式。不要自动插值、裁切或改Ms。'),
 ('identity','恢复身份不一致','核对材料、网格、核和dt；改物理参数请明确作为新初态，不冒充精确恢复。'),
 ('structure','目标磁结构不符合','可能是真实弛豫、边界或初态效应；先核身份与单位，再分别做dt、网格、镜像敏感性检查。不要自动调D/K/场保住skyrmion。'),
 ('residual','静态末态尚未达请求阈值','查看A/B各自残差和停止原因；合理延长资源或恢复。中间峰值不否定已达标保存态，也不要自动放宽阈值。')]
def hints(state):
 if isinstance(state,dict):
  tags=[]
  if state.get('static_criterion',{}).get('status')=='not_met':tags.append('residual')
  if state.get('structure_goal',{}).get('status')=='not_met':tags.append('structure')
  # Successful native reason residual_tolerance is a stop code, never a failure tag.
  if state.get('execution_completed'):return [{'observed':'请求的流程和独立判据已完成','guidance':'按报告分别查看步长敏感性、结构目标与未检查的网格/镜像收敛；不自动改变参数。','automatic_parameter_change':False}]
  reason=' '.join(tags+[state.get('failure_detail',''),state.get('stop_reason','') if state.get('stop_reason')!='residual_tolerance' else ''])
 else:reason=str(state)
 result=[{'observed':title,'guidance':text,'automatic_parameter_change':False} for tag,title,text in RULES if tag.lower() in reason.lower()]
 return result or [{'observed':reason,'guidance':'查看report.json和native stderr，先核对输入/单位及最后完整状态，再有针对性复核。','automatic_parameter_change':False}]
