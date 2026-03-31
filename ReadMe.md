该版本将各类参数使用PV进行配置，不在config.yaml中配置。
  power_targets: [10,20,30]
  wait_time_default: 1.0    # wait_time PV读取失败时的默认等待时间 (秒)，每次展脉宽等待时间
  wait_after_expand: 10.0    # 每次展脉宽结束后、开始调功率前的等待时间 (秒)
  pulse_step: 0.5           # 脉宽步长 (ms)，临时从config读取，后续改回PV
  