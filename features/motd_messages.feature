Feature: MOTD Messages

    @series.xenial
    @series.bionic
    @uses.config.machine_type.lxd.container
    Scenario Outline: Contract update prevents contract expiration messages
        Given a `<release>` machine with ubuntu-advantage-tools installed
        When I run `apt-get update` with sudo
        When I attach `contract_token` with sudo
        When I update contract to use `effectiveTo` as `$behave_var{today +2}`
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout does not match regexp:
        """
        [\w\d.]+

        CAUTION: Your Ubuntu Pro subscription will expire in 2 days.
        Renew your subscription at https:\/\/ubuntu.com\/pro to ensure continued security
        coverage for your applications.

        [\w\d.]+
        """
        When I update contract to use `effectiveTo` as `$behave_var{today -3}`
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout does not match regexp:
        """
        [\w\d.]+

        CAUTION: Your Ubuntu Pro subscription expired on \d+ \w+ \d+.
        Renew your subscription at https:\/\/ubuntu.com\/pro to ensure continued security
        coverage for your applications.
        Your grace period will expire in 11 days.

        [\w\d.]+
        """
        When I update contract to use `effectiveTo` as `$behave_var{today -20}`
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout does not match regexp:
        """
        [\w\d.]+

        \*Your Ubuntu Pro subscription has EXPIRED\*
        \d+ additional security update\(s\) require Ubuntu Pro with '<service>' enabled.
        Renew your service at https:\/\/ubuntu.com\/pro

        [\w\d.]+
        """
        Examples: ubuntu release
           | release | service   |
           | xenial  | esm-infra |
           | bionic  | esm-apps  |


    @series.xenial
    @series.bionic
    @uses.config.machine_type.lxd.container
    Scenario Outline: Contract Expiration Messages
        Given a `<release>` machine with ubuntu-advantage-tools installed
        When I run `apt-get update` with sudo
        And I run `apt-get install ansible -y` with sudo
        And I attach `contract_token` with sudo
        And I set the machine token overlay to the following yaml
        """
        machineTokenInfo:
          contractInfo:
            effectiveTo: $behave_var{today +2}
        """
        And I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout matches regexp:
        """
        [\w\d.]+

        CAUTION: Your Ubuntu Pro subscription will expire in 2 days.
        Renew your subscription at https:\/\/ubuntu.com\/pro to ensure continued security
        coverage for your applications.

        [\w\d.]+
        """
        When I set the machine token overlay to the following yaml
        """
        machineTokenInfo:
          contractInfo:
            effectiveTo: $behave_var{today -3}
        """
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout matches regexp:
        """
        [\w\d.]+

        CAUTION: Your Ubuntu Pro subscription expired on \d+ \w+ \d+.
        Renew your subscription at https:\/\/ubuntu.com\/pro to ensure continued security
        coverage for your applications.
        Your grace period will expire in 11 days.

        [\w\d.]+
        """
        When I set the machine token overlay to the following yaml
        """
        machineTokenInfo:
          contractInfo:
            effectiveTo: $behave_var{today -20}
        """
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout matches regexp:
        """
        [\w\d.]+

        \*Your Ubuntu Pro subscription has EXPIRED\*
        \d+ additional security update\(s\) require Ubuntu Pro with '<service>' enabled.
        Renew your service at https:\/\/ubuntu.com\/pro

        [\w\d.]+
        """
        When I run `apt-get upgrade -y` with sudo
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout matches regexp:
        """
        [\w\d.]+

        \*Your Ubuntu Pro subscription has EXPIRED\*
        Renew your service at https:\/\/ubuntu.com\/pro

        [\w\d.]+
        """
        When I create the file `/tmp/machine-token-overlay.json` with the following:
        """
        {
            "machineTokenInfo": {
                "contractInfo": {
                    "effectiveTo": null
                }
            }
        }
        """
        When I wait `1` seconds
        When I run `pro refresh messages` with sudo
        And I run `run-parts /etc/update-motd.d/` with sudo
        Then stdout matches regexp:
        """
        [\w\d.]+

        \*Your Ubuntu Pro subscription has EXPIRED\*
        Renew your service at https:\/\/ubuntu.com\/pro

        [\w\d.]+
        """
        Examples: ubuntu release
           | release | service   |
           | xenial  | esm-infra |
           | bionic  | esm-apps  |
