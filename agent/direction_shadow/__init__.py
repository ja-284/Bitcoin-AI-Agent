"""
The prospective direction shadow track (E034, research/DIRECTION_TRACK.md): the frozen 1h direction probability
`direction_1h_v1`, scored every hour into its own table (`shadow_direction`). Research only. It never touches the
live BUY/HOLD/SELL decision, the move-size shadow record or any checkpoint, and it never trades.
"""
