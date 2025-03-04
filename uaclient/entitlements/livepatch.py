import logging
import re
from typing import Any, Dict, Optional, Tuple

from uaclient import (
    apt,
    event_logger,
    exceptions,
    livepatch,
    messages,
    snap,
    system,
    util,
)
from uaclient.entitlements.base import IncompatibleService, UAEntitlement
from uaclient.entitlements.entitlement_status import ApplicationStatus
from uaclient.types import StaticAffordance

LIVEPATCH_RETRIES = [0.5, 1.0]

ERROR_MSG_MAP = {
    "Unknown Auth-Token": "Invalid Auth-Token provided to livepatch.",
    "unsupported kernel": "Your running kernel is not supported by Livepatch.",
}

event = event_logger.get_event_logger()


class LivepatchEntitlement(UAEntitlement):

    help_doc_url = "https://ubuntu.com/security/livepatch"
    name = "livepatch"
    title = "Livepatch"
    description = "Canonical Livepatch service"
    affordance_check_arch = False
    affordance_check_series = False
    affordance_check_kernel_min_version = False
    affordance_check_kernel_flavor = False

    @property
    def incompatible_services(self) -> Tuple[IncompatibleService, ...]:
        from uaclient.entitlements.fips import FIPSEntitlement
        from uaclient.entitlements.realtime import RealtimeKernelEntitlement

        return (
            IncompatibleService(
                FIPSEntitlement, messages.LIVEPATCH_INVALIDATES_FIPS
            ),
            IncompatibleService(
                RealtimeKernelEntitlement,
                messages.REALTIME_LIVEPATCH_INCOMPATIBLE,
            ),
        )

    @property
    def static_affordances(self) -> Tuple[StaticAffordance, ...]:
        # Use a lambda so we can mock system.is_container in tests
        from uaclient.entitlements.fips import FIPSEntitlement

        fips_ent = FIPSEntitlement(self.cfg)

        is_fips_enabled = bool(
            fips_ent.application_status()[0] == ApplicationStatus.ENABLED
        )

        return (
            (
                messages.LIVEPATCH_ERROR_INSTALL_ON_CONTAINER,
                lambda: system.is_container(),
                False,
            ),
            (
                messages.LIVEPATCH_ERROR_WHEN_FIPS_ENABLED,
                lambda: is_fips_enabled,
                False,
            ),
        )

    def _perform_enable(self, silent: bool = False) -> bool:
        """Enable specific entitlement.

        @return: True on success, False otherwise.
        """
        if not system.which(snap.SNAP_CMD):
            event.info("Installing snapd")
            event.info(messages.APT_UPDATING_LISTS)
            try:
                apt.run_apt_update_command()
            except exceptions.UserFacingError as e:
                logging.debug(
                    "Trying to install snapd."
                    " Ignoring apt-get update failure: %s",
                    str(e),
                )
            try:
                system.subp(
                    ["apt-get", "install", "--assume-yes", "snapd"],
                    retry_sleeps=apt.APT_RETRIES,
                )
            except exceptions.ProcessExecutionError:
                raise exceptions.CannotInstallSnapdError()

        elif not snap.is_installed():
            raise exceptions.SnapdNotProperlyInstalledError(
                snap_cmd=snap.SNAP_CMD, service=self.title
            )

        try:
            system.subp(
                [snap.SNAP_CMD, "wait", "system", "seed.loaded"], capture=True
            )
        except exceptions.ProcessExecutionError as e:
            if re.search(r"unknown command .*wait", str(e).lower()):
                logging.warning(messages.SNAPD_DOES_NOT_HAVE_WAIT_CMD)
            else:
                raise

        http_proxy = util.validate_proxy(
            "http", self.cfg.http_proxy, util.PROXY_VALIDATION_SNAP_HTTP_URL
        )
        https_proxy = util.validate_proxy(
            "https", self.cfg.https_proxy, util.PROXY_VALIDATION_SNAP_HTTPS_URL
        )
        snap.configure_snap_proxy(
            http_proxy=http_proxy,
            https_proxy=https_proxy,
            retry_sleeps=snap.SNAP_INSTALL_RETRIES,
        )

        if not livepatch.is_livepatch_installed():
            event.info("Installing canonical-livepatch snap")
            try:
                system.subp(
                    [snap.SNAP_CMD, "install", "canonical-livepatch"],
                    capture=True,
                    retry_sleeps=snap.SNAP_INSTALL_RETRIES,
                )
            except exceptions.ProcessExecutionError as e:
                raise exceptions.ErrorInstallingLivepatch(error_msg=str(e))

        livepatch.configure_livepatch_proxy(http_proxy, https_proxy)

        return self.setup_livepatch_config(
            process_directives=True, process_token=True
        )

    def setup_livepatch_config(
        self, process_directives: bool = True, process_token: bool = True
    ) -> bool:
        """Processs configuration setup for livepatch directives.

        :param process_directives: Boolean set True when directives should be
            processsed.
        :param process_token: Boolean set True when token should be
            processsed.
        """
        entitlement_cfg = self.cfg.machine_token_file.entitlements.get(
            self.name
        )
        if process_directives:
            try:
                process_config_directives(entitlement_cfg)
            except exceptions.ProcessExecutionError as e:
                msg = "Unable to configure Livepatch: " + str(e)
                event.info(msg)
                logging.error(msg)
                return False
        if process_token:
            livepatch_token = entitlement_cfg.get("resourceToken")
            if not livepatch_token:
                logging.debug(
                    "No specific resourceToken present. Using machine token as"
                    " %s credentials",
                    self.title,
                )
                livepatch_token = self.cfg.machine_token["machineToken"]
            application_status, _details = self.application_status()
            if application_status != ApplicationStatus.DISABLED:
                logging.info(
                    "Disabling %s prior to re-attach with new token",
                    self.title,
                )
                try:
                    system.subp([livepatch.LIVEPATCH_CMD, "disable"])
                except exceptions.ProcessExecutionError as e:
                    logging.error(str(e))
                    return False
            try:
                system.subp(
                    [livepatch.LIVEPATCH_CMD, "enable", livepatch_token],
                    capture=True,
                )
            except exceptions.ProcessExecutionError as e:
                msg = "Unable to enable Livepatch: "
                for error_message, print_message in ERROR_MSG_MAP.items():
                    if error_message in str(e):
                        msg += print_message
                        break
                if msg == "Unable to enable Livepatch: ":
                    msg += str(e)
                event.info(msg)
                return False
            event.info("Canonical livepatch enabled.")
        return True

    def _perform_disable(self, silent=False):
        """Disable specific entitlement

        @return: True on success, False otherwise.
        """
        if not livepatch.is_livepatch_installed():
            return True
        system.subp([livepatch.LIVEPATCH_CMD, "disable"], capture=True)
        return True

    def application_status(
        self,
    ) -> Tuple[ApplicationStatus, Optional[messages.NamedMessage]]:
        status = (ApplicationStatus.ENABLED, None)

        if not livepatch.is_livepatch_installed():
            return (ApplicationStatus.DISABLED, messages.LIVEPATCH_NOT_ENABLED)

        if livepatch.status() is None:
            # TODO(May want to parse INACTIVE/failure assessment)
            return (
                ApplicationStatus.DISABLED,
                messages.LIVEPATCH_APPLICATION_STATUS_CLIENT_FAILURE,
            )
        return status

    def enabled_warning_status(
        self,
    ) -> Tuple[bool, Optional[messages.NamedMessage]]:
        if livepatch.on_supported_kernel() is False:
            kernel_info = system.get_kernel_info()
            arch = system.get_lscpu_arch()
            return (
                True,
                messages.LIVEPATCH_KERNEL_NOT_SUPPORTED.format(
                    version=kernel_info.uname_release, arch=arch
                ),
            )
        # if on_supported_kernel returns None we default to no warning
        # because there would be no way for a user to resolve the warning
        return False, None

    def status_description_override(self):
        if (
            livepatch.on_supported_kernel() is False
            and not system.is_container()
        ):
            return messages.LIVEPATCH_KERNEL_NOT_SUPPORTED_DESCRIPTION
        return None

    def process_contract_deltas(
        self,
        orig_access: Dict[str, Any],
        deltas: Dict[str, Any],
        allow_enable: bool = False,
    ) -> bool:
        """Process any contract access deltas for this entitlement.

        :param orig_access: Dictionary containing the original
            resourceEntitlement access details.
        :param deltas: Dictionary which contains only the changed access keys
        and values.
        :param allow_enable: Boolean set True if allowed to perform the enable
            operation. When False, a message will be logged to inform the user
            about the recommended enabled service.

        :return: True when delta operations are processed; False when noop.
        """
        if super().process_contract_deltas(orig_access, deltas, allow_enable):
            return True  # Already processed parent class deltas

        delta_entitlement = deltas.get("entitlement", {})
        process_enable_default = delta_entitlement.get("obligations", {}).get(
            "enabledByDefault", False
        )

        if process_enable_default:
            enable_success, _ = self.enable()
            return enable_success

        application_status, _ = self.application_status()
        if application_status == ApplicationStatus.DISABLED:
            return False  # only operate on changed directives when ACTIVE
        delta_directives = delta_entitlement.get("directives", {})
        supported_deltas = set(["caCerts", "remoteServer"])
        process_directives = bool(
            supported_deltas.intersection(delta_directives)
        )
        process_token = bool(deltas.get("resourceToken", False))
        if any([process_directives, process_token]):
            logging.info("Updating '%s' on changed directives.", self.name)
            return self.setup_livepatch_config(
                process_directives=process_directives,
                process_token=process_token,
            )
        return True


def process_config_directives(cfg):
    """Process livepatch configuration directives.

    We process caCerts before remoteServer because changing remote-server
    in the canonical-livepatch CLI performs a PUT against the new server name.
    If new caCerts were required for the new remoteServer, this
    canonical-livepatch client PUT could fail on unmatched old caCerts.

    @raises: ProcessExecutionError if unable to configure livepatch.
    """
    if not cfg:
        return
    directives = cfg.get("entitlement", {}).get("directives", {})
    ca_certs = directives.get("caCerts")
    if ca_certs:
        system.subp(
            [
                livepatch.LIVEPATCH_CMD,
                "config",
                "ca-certs={}".format(ca_certs),
            ],
            capture=True,
        )
    remote_server = directives.get("remoteServer", "")
    if remote_server.endswith("/"):
        remote_server = remote_server[:-1]
    if remote_server:
        system.subp(
            [
                livepatch.LIVEPATCH_CMD,
                "config",
                "remote-server={}".format(remote_server),
            ],
            capture=True,
        )
