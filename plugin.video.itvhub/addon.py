# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2022-2023 Dimitri Kroon.
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  This file is part of plugin.video.itvx
# ----------------------------------------------------------------------------------------------------------------------
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  This file is part of plugin.video.itvx
# ---------------------------------------------------------------------------------------------------------------------


from codequick import support
from resources.lib import addon_log
from resources.lib import main
from resources.lib import utils
from resources.lib import cc_patch


cc_patch.patch_cc_route()
cc_patch.patch_label_prop()


if __name__ == '__main__':
    utils.addon_info.initialise()
    main.run()
    addon_log.shutdown_log()
